"""Video night shift: my saved tech videos, turned into searchable notes while I sleep.

I save technical videos on X and never watch them again, and my bookmark tool only reads text. Overnight, only while
the laptop is plugged in (light is on), this:
  1. picks saved videos whose post text is technical (code, a keyword rule) and 3 minutes or less (yt-dlp metadata),
  2. writes out the speech with Whisper small (open model, on the CPU),
  3. asks Gemma 4 E2B (open weights, Ollama) for notes: kind, tools, main claim + exact quote, numbers, and the names
     Whisper misheard, fixed from the post text ("Olamar" -> "Ollama"),
  4. checks every note (guard), one retry, then "not read" - and keeps the notes in out/night.db for search.

Usage: python videoshift.py [--limit 20] [--until 07:00] [--fake-power FILE]
       python videoshift.py search <words>
"""
import argparse, datetime as dt, html, json, os, re, sqlite3, subprocess, sys, time
from pathlib import Path

from nightshift import (OUT, SRC_DB, MODEL, SECRET, WAT, log, http_json, wait_for_power, now)

FFMPEG_DIR = r"C:\Users\DELL\tools\testreel\node_modules\ffmpeg-static"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ["PATH"]
PY = sys.executable
AUD = OUT / "audio"; AUD.mkdir(parents=True, exist_ok=True)
DB = OUT / "night.db"; PAGE = OUT / "video_notes.html"
MAX_S, MIN_WORDS = 180, 10
TECH = re.compile(r"\b(ai|llm|llms|agent|agents|agentic|model|models|gpt|claude|gemini|gemma|llama|qwen|code|coding|coder|"
                  r"python|javascript|typescript|rust|api|gpu|cuda|vram|inference|fine-?tun\w*|rag|mcp|cursor|copilot|"
                  r"open[- ]?source|github|repo|demo|tutorial|benchmark|prompt\w*|token\w*|deploy\w*|cloudflare|workers?|"
                  r"database|sql|tech|engineer\w*|developer|dev|startup|robot\w*|automat\w*)\b", re.I)
KINDS = ("launch", "how-to", "talk", "other")

PROMPT = """You turn a short saved video into notes I can search later.

The post that shared the video (names in the post are spelled correctly):
\"\"\"{post}\"\"\"

What is said in the video (automatic transcript; product and model names may be misheard):
\"\"\"{transcript}\"\"\"

Answer with JSON only:
{{"kind": "launch" or "how-to" or "talk" or "other",
 "tools": ["product, model or library names mentioned, spelled as in the post when the post has them"],
 "claim": "the one main point of the video, one sentence",
 "quote": "exact words copied from the transcript that support the claim",
 "numbers": ["figures that are said, copied exactly"],
 "fixes": [{{"heard": "a name as written in the transcript", "means": "the same name as spelled in the post"}}]}}
Use only what the post and the transcript say.{retry}"""

norm = lambda s: re.sub(r"[^\w$%.]+", " ", (s or "").lower()).strip()

def guard(raw, post, transcript):
    """The model may only label and copy: every name, quote and number must be in the post or the transcript."""
    try: v = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw or "", re.S)
        try: v = json.loads(m.group(0)) if m else None
        except Exception: v = None
    if not isinstance(v, dict): return None, ["no_json"]
    P, T = norm(post), norm(transcript); both = P + " " + T
    r = []
    if v.get("kind") not in KINDS: r.append("bad_kind")
    tools = v.get("tools") or []
    if not isinstance(tools, list) or len(tools) > 8: r.append("bad_tools")
    else: r += [f"tool_not_in_source:{t}" for t in tools if not norm(str(t)) or norm(str(t)) not in both]
    claim = str(v.get("claim") or "").strip()
    if not claim or len(claim.split()) > 35: r.append("bad_claim")
    q = norm(str(v.get("quote") or ""))
    if len(q) < 12 or q not in T: r.append("quote_not_in_transcript")
    nums = v.get("numbers") or []
    if not isinstance(nums, list): r.append("bad_numbers")
    else:
        src_digits = set(re.findall(r"\d+", post + " " + transcript))
        r += [f"number_not_said:{n}" for n in nums for d in re.findall(r"\d+", str(n)) if d not in src_digits]
    fixes = v.get("fixes") or []
    if not isinstance(fixes, list): r.append("bad_fixes")
    else:
        for f in fixes:
            h, m = norm(str((f or {}).get("heard"))), norm(str((f or {}).get("means")))
            if not h or not m or h == m or h not in T or m not in P: r.append(f"bad_fix:{(f or {}).get('heard')}")
    if r: return None, r
    v["tools"] = [str(t).strip() for t in tools]; v["claim"] = claim; v["quote"] = str(v["quote"]).strip()
    # Gemma finds the misheard names; code applies the checked fixes to tools and claim (the quote stays word for word).
    for f in fixes:
        pat = re.compile(re.escape(str(f["heard"]).strip()), re.I)
        v["claim"] = pat.sub(str(f["means"]).strip(), v["claim"])
        v["tools"] = [pat.sub(str(f["means"]).strip(), t) for t in v["tools"]]
    v["tools"] = list(dict.fromkeys(v["tools"]))
    return v, []

def ask(post, transcript, retry_reasons):
    retry = f"\nYour last answer was refused because: {', '.join(retry_reasons)}. Fix only that." if retry_reasons else ""
    body = {"model": MODEL, "stream": False, "think": False, "format": "json", "options": {"temperature": 0, "num_predict": 400},
            "messages": [{"role": "user", "content": PROMPT.format(post=post[:900], transcript=transcript[:3500], retry=retry)}]}
    return http_json("http://127.0.0.1:11434/api/chat", body, timeout=300)["message"]["content"]

def notes_for(post, transcript):
    reasons, calls = [], 0
    for _ in range(2):                                    # one retry, then not read
        calls += 1
        v, reasons = guard(ask(post, transcript, reasons), post, transcript)
        if v: return v, calls, []
    return None, calls, reasons

# ---------- video steps ----------
def duration(url):
    p = subprocess.run([PY, "-m", "yt_dlp", "-J", "--no-warnings", "--skip-download", url], capture_output=True, text=True, timeout=90)
    if p.returncode: return None, "blocked: " + ((p.stderr.strip().splitlines() or ["?"])[-1][:100])
    j = json.loads(p.stdout); e = (j.get("entries") or [j])[0]
    return e.get("duration"), None

def audio(bid, url):
    for f in AUD.glob(f"{bid}.*"): f.unlink()
    p = subprocess.run([PY, "-m", "yt_dlp", "-q", "--no-warnings", "-f", "bestaudio/best", "--ffmpeg-location", FFMPEG_DIR,
                        "-o", str(AUD / f"{bid}.%(ext)s"), url], capture_output=True, text=True, timeout=240)
    f = next(iter(sorted(AUD.glob(f"{bid}.*"))), None)
    return (f, None) if (f and not p.returncode) else (None, "download_failed")

def open_db():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    con.execute("""create table if not exists videos (id text primary key, run text, at text, status text, duration real,
                   transcript text, notes text, calls int, reasons text, asr_s real, gemma_s real)""")
    con.execute("create table if not exists video_runs (run text primary key, started text, ended text, done int, paused_s int, stopped text)")
    return con

def todo(con, limit):
    src = sqlite3.connect(SRC_DB); src.row_factory = sqlite3.Row
    seen = {r[0] for r in con.execute("select id from videos")}
    rows = src.execute("select id, text, url, author_username from bookmarks where source='bookmark' and media_json like '%\"video\"%' "
                       "order by created_at desc").fetchall()
    return [r for r in rows if r["id"] not in seen and TECH.search(r["text"] or "")][:limit]

def save(con, run, bid, status, **kw):
    con.execute("insert or replace into videos values(?,?,?,?,?,?,?,?,?,?,?)",
                (bid, run, now().isoformat(), status, kw.get("duration"), kw.get("transcript"),
                 json.dumps(kw["notes"]) if kw.get("notes") else None, kw.get("calls", 0),
                 json.dumps(kw.get("reasons", [])), kw.get("asr_s"), kw.get("gemma_s")))
    con.commit()

# ---------- page and search ----------
def page(con, run):
    src = sqlite3.connect(SRC_DB); src.row_factory = sqlite3.Row
    rows = con.execute("select * from videos where run=? order by at", (run,)).fetchall()
    info = con.execute("select * from video_runs where run=?", (run,)).fetchone()
    cnt = {}
    for r in rows: k = r["status"].split(":")[0]; cnt[k] = cnt.get(k, 0) + 1
    cards = []
    for r in rows:
        if r["status"] != "ok": continue
        b = src.execute("select author_username, url from bookmarks where id=?", (r["id"],)).fetchone()
        n = json.loads(r["notes"]); e = html.escape
        fixes = "".join(f'<li>heard “{e(f["heard"])}”, means <b>{e(f["means"])}</b></li>' for f in n.get("fixes") or [])
        cards.append(f'<article><p class="kind">{e(n["kind"])} · {round(r["duration"] or 0)} s · @{e(b["author_username"] or "")}</p>'
                     f'<p class="claim">{e(n["claim"])}</p><blockquote>“{e(SECRET.sub("[hidden]", n["quote"]))}”</blockquote>'
                     + (f'<p class="tools">{" · ".join(e(t) for t in n["tools"])}</p>' if n["tools"] else "")
                     + (f'<p class="nums">{" · ".join(e(str(x)) for x in n.get("numbers") or [])}</p>' if n.get("numbers") else "")
                     + (f'<ul class="fix">{fixes}</ul>' if fixes else "")
                     + f'<p class="meta"><a href="{e(b["url"] or "")}">open the video</a></p></article>')
    paused = round((info["paused_s"] or 0) / 60) if info else 0
    summary = (f"{cnt.get('ok', 0)} videos turned into notes. Skipped: {cnt.get('too_long', 0)} longer than 3 min, "
               f"{cnt.get('silent', 0)} with no speech, {cnt.get('blocked', 0) + cnt.get('download_failed', 0)} not reachable, "
               f"{cnt.get('not_read', 0)} notes refused by the check." + (f" Paused {paused} min on battery." if paused else ""))
    PAGE.write_text(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video notes · {run}</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:680px;margin:0 auto;padding:24px 16px;background:#f6f7f9;color:#16181d}}
h1{{font-size:1.4rem;margin:0 0 4px}}.sum{{color:#555b66;margin:0 0 22px}}article{{background:#fff;border:1px solid #e1e4ea;border-radius:12px;padding:14px 16px;margin:0 0 14px}}
.kind{{margin:0;font-size:.8rem;text-transform:uppercase;letter-spacing:.05em;color:#6a7280}}.claim{{margin:6px 0;font-weight:650}}
blockquote{{margin:6px 0;padding-left:12px;border-left:3px solid #d5dae3;color:#363b45}}.tools{{margin:6px 0;color:#1d4ed8;font-weight:600}}
.nums{{margin:4px 0;color:#7c2d12}}.fix{{margin:6px 0;padding-left:18px;color:#555b66;font-size:.92rem}}.meta{{margin:6px 0 0;font-size:.9rem}}</style>
<h1>Your saved videos, as notes</h1><p class="sum">{html.escape(summary)}</p>{"".join(cards) or "<p>No new notes.</p>"}""", encoding="utf8")
    return cnt.get("ok", 0)

def search(words):
    con = open_db(); q = norm(words)
    for r in con.execute("select * from videos where status='ok'"):
        n = json.loads(r["notes"]); hay = norm(" ".join([n["claim"], " ".join(n["tools"]), r["transcript"] or ""]))
        if all(w in hay for w in q.split()):
            print(f"- {n['claim']}\n  tools: {', '.join(n['tools'])}\n  “{n['quote']}”\n")

# ---------- main ----------
def main():
    if len(sys.argv) > 2 and sys.argv[1] == "search": return search(" ".join(sys.argv[2:]))
    ap = argparse.ArgumentParser(); ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--until", default="07:00"); ap.add_argument("--fake-power"); a = ap.parse_args()
    start = now(); h, m = map(int, a.until.split(":"))
    deadline = start.replace(hour=h, minute=m, second=0, microsecond=0)
    if deadline <= start: deadline += dt.timedelta(days=1)
    run = start.strftime("%Y-%m-%d-%H%M")
    con = open_db(); items = todo(con, a.limit)
    con.execute("insert or replace into video_runs(run, started, done, paused_s) values(?,?,0,0)", (run, start.isoformat())); con.commit()
    log("video_start", run=run, todo=len(items)); print(f"video shift {run}: {len(items)} saved tech videos, until {deadline:%H:%M} WAT", flush=True)
    import whisper
    model = whisper.load_model("small", device="cpu")
    paused, stopped = 0, "done"
    for i, r in enumerate(items, 1):
        if now() >= deadline: stopped = "until"; break
        p = wait_for_power(deadline, a.fake_power)
        if p is None: stopped = "until_on_battery"; break
        paused += p
        dur, err = duration(r["url"])
        if err: save(con, run, r["id"], "blocked"); print(f"{i:3} blocked"); continue
        if dur is None or dur > MAX_S: save(con, run, r["id"], "too_long", duration=dur); print(f"{i:3} too long ({dur})"); continue
        f, err = audio(r["id"], r["url"])
        if err: save(con, run, r["id"], err, duration=dur); print(f"{i:3} {err}"); continue
        t0 = time.time()
        try: transcript = model.transcribe(str(f), fp16=False)["text"].strip()
        except Exception: transcript = ""                      # e.g. a clip with no sound track
        asr_s = round(time.time() - t0, 1); f.unlink(missing_ok=True)   # keep text only, not the audio
        if len(transcript.split()) < MIN_WORDS:
            save(con, run, r["id"], "silent", duration=dur, transcript=transcript, asr_s=asr_s); print(f"{i:3} silent"); continue
        if wait_for_power(deadline, a.fake_power) is None: stopped = "until_on_battery"; break
        t0 = time.time(); notes, calls, reasons = notes_for(r["text"] or "", transcript); g_s = round(time.time() - t0, 1)
        save(con, run, r["id"], "ok" if notes else "not_read", duration=dur, transcript=transcript, notes=notes,
             calls=calls, reasons=reasons, asr_s=asr_s, gemma_s=g_s)
        con.execute("update video_runs set done=?, paused_s=? where run=?", (i, paused, run)); con.commit()
        print(f"{i:3} {'ok' if notes else 'not read'}  whisper {asr_s}s  gemma {g_s}s  calls {calls}  {reasons if reasons else ''}", flush=True)
    con.execute("update video_runs set ended=?, stopped=?, paused_s=? where run=?", (now().isoformat(), stopped, paused, run)); con.commit()
    n = page(con, run); log("video_end", run=run, notes=n, stopped=stopped, paused_s=paused)
    print(f"done ({stopped}). {n} notes. Page: {PAGE}")

if __name__ == "__main__":
    main()
