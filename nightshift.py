"""Night shift: a local Gemma reads the day's new bookmarks overnight, only while the laptop is plugged in,
and leaves a short morning page of the few worth reading for what I am writing now.

- Gemma 4 E2B (open weights) via Ollama (open-source runtime) makes every reading decision.
- Code does only what code is sure about: skip posts that are mostly a link, check every answer (guard),
  and pause the moment the laptop drops to battery (light gone), resuming when it is plugged in again.
- One retry per post, then "unclear". The only waiting loop is for power, and it stops at --until.

Usage: python nightshift.py [--limit 150] [--until 07:00] [--fake-power FILE]
"""
import argparse, datetime as dt, html, json, re, sqlite3, time, urllib.request
from pathlib import Path

import psutil

MODEL = "gemma4:e2b-it-qat"
SRC_DB = Path.home() / ".bookmark-cli" / "bookmarks.db"
OUT = Path(__file__).parent / "out"; OUT.mkdir(exist_ok=True)
NIGHT_DB, EVENTS, PROFILE_CACHE, PAGE = OUT / "night.db", OUT / "events.jsonl", OUT / "profile.json", OUT / "morning.html"
WAT = dt.timezone(dt.timedelta(hours=1))

# ---------- frozen on 2026-10-22 (after labels set 1; set 2 is the clean test) ----------
MIN_OWN_WORDS = 8          # fewer words than this, besides links and @handles: "mostly a link", Gemma not asked
PROMPT = """You help me decide which saved posts are worth reading today.

What I am writing about now (my latest posts):
{profile}

A post I saved:
\"\"\"{text}\"\"\"

Score how useful this post is for what I am writing now:
0 = not related, 1 = loosely related,
2 = the post itself contains an idea, finding or tool I could use in what I am writing,
3 = read it today: it speaks directly to one of my topics.
Do not give 2 or 3 for general advice, quotes or posts whose point is only behind a link.
Answer with JSON only: {{"score": 0-3, "why": "one short sentence", "quote": "a few exact words copied from the post"}}{retry}"""
# -----------------------------------------------------------------------------------------

SECRET = re.compile(r"\b(?:[a-z]{2,4}_)?(?:sk|pk|key|tok)[_-][A-Za-z0-9_\-]{12,}\b|\b[A-Za-z0-9_\-]{32,}\b")
norm = lambda s: re.sub(r"\s+", " ", s or "").strip().lower()
now = lambda: dt.datetime.now(WAT)

def log(event, **kw):
    with open(EVENTS, "a", encoding="utf8") as f:
        f.write(json.dumps({"at": now().isoformat(timespec="seconds"), "event": event, **kw}) + "\n")

def http_json(url, body=None, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "night-shift"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def get_profile():
    """My last 6 DEV posts, live; the cached copy if the network is down."""
    try:
        posts = http_json("https://dev.to/api/articles?username=dannwaneri&per_page=6", timeout=20)
        prof = "\n".join(f"- {p['title']}: {(p.get('description') or '')[:160]}" for p in posts)
        PROFILE_CACHE.write_text(json.dumps({"at": now().isoformat(), "profile": prof}), encoding="utf8")
        return prof
    except Exception as e:
        log("profile_cached", error=str(e)[:120])
        return json.loads(PROFILE_CACHE.read_text(encoding="utf8"))["profile"]

def own_words(text):
    return len(re.sub(r"https?://\S+|@\w+", " ", text or "").split())

def guard(raw, text):
    reasons = []
    try:
        v = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw or "", re.S)
        try: v = json.loads(m.group(0)) if m else None
        except Exception: v = None
    if not isinstance(v, dict): return None, ["no_json"]
    if v.get("score") not in (0, 1, 2, 3): reasons.append("bad_score")
    why = str(v.get("why") or "").strip()
    if not why or len(why.split()) > 30: reasons.append("bad_why")
    q = norm(str(v.get("quote") or ""))
    if len(q) < 4 or q not in norm(text): reasons.append("quote_not_in_post")
    return (v if not reasons else None), reasons

def ask(profile, text, retry_reasons):
    retry = f"\nYour last answer was refused because: {', '.join(retry_reasons)}. Fix only that." if retry_reasons else ""
    body = {"model": MODEL, "stream": False, "think": False, "format": "json",
            "options": {"temperature": 0, "num_predict": 120},
            "messages": [{"role": "user", "content": PROMPT.format(profile=profile, text=text[:900], retry=retry)}]}
    return http_json("http://127.0.0.1:11434/api/chat", body)["message"]["content"]

def read_post(profile, text):
    """Returns (status, score, why, quote, calls, reasons). One retry, then unclear."""
    if own_words(text) < MIN_OWN_WORDS:
        return "link_only", None, None, None, 0, []
    reasons, calls = [], 0
    for _ in range(2):
        calls += 1
        v, reasons = guard(ask(profile, text, reasons), text)
        if v: return "ok", v["score"], v["why"].strip(), v["quote"].strip(), calls, []
    return "unclear", None, None, None, calls, reasons

# ---------- power ----------
def plugged(fake=None):
    if fake:                                  # tests: a file containing "on" or "off"
        return Path(fake).read_text().strip() == "on"
    b = psutil.sensors_battery()
    return True if b is None else bool(b.power_plugged)

def wait_for_power(deadline, fake=None, poll_s=30):
    """Block while on battery. Returns seconds paused, or None if --until passed while waiting."""
    if plugged(fake): return 0
    t0 = time.time(); log("pause", reason="on battery (light gone)")
    print("  light gone: on battery, pausing…", flush=True)
    while not plugged(fake):
        if now() >= deadline:
            log("stop_waiting", paused_s=round(time.time() - t0)); return None
        time.sleep(poll_s)
    paused = round(time.time() - t0); log("resume", paused_s=paused)
    print(f"  plugged in again after {paused} s, resuming", flush=True)
    # A long outage (or a sleeping laptop) can outlast the time limit: power came back at 09:01 after a 03:00 limit
    # on 23 Oct, and the run went on. Check the limit again before working.
    if now() >= deadline:
        log("stop_after_resume", paused_s=paused); return None
    return paused

# ---------- storage ----------
def open_night():
    con = sqlite3.connect(NIGHT_DB); con.row_factory = sqlite3.Row
    con.execute("""create table if not exists reads (id text primary key, run text, at text, status text, score int,
                   why text, quote text, calls int, reasons text, s real)""")
    con.execute("create table if not exists runs (run text primary key, started text, ended text, read int, paused_s int, stopped text)")
    return con

def todo(night, limit):
    src = sqlite3.connect(SRC_DB); src.row_factory = sqlite3.Row
    done = {r[0] for r in night.execute("select id from reads")}
    rows = src.execute("select id, text, author_username, url, likes, bookmark_added_at from bookmarks "
                       "where source='bookmark' order by bookmark_added_at desc, created_at desc limit ?", (limit * 4,)).fetchall()
    return [r for r in rows if r["id"] not in done][:limit]

# ---------- morning page ----------
def morning_page(night, run):
    src = sqlite3.connect(SRC_DB); src.row_factory = sqlite3.Row
    reads = night.execute("select * from reads where run=?", (run,)).fetchall()
    info = night.execute("select * from runs where run=?", (run,)).fetchone()
    picks = sorted([r for r in reads if r["status"] == "ok" and r["score"] >= 2], key=lambda r: (-r["score"], r["at"]))
    cnt = lambda st: sum(1 for r in reads if r["status"] == st)
    def card(r):
        b = src.execute("select text, author_username, url from bookmarks where id=?", (r["id"],)).fetchone()
        text = html.escape(SECRET.sub("[hidden]", re.sub(r"\s+", " ", b["text"] or ""))[:320])
        tag = "Read today" if r["score"] == 3 else "Worth a look"
        return (f'<article><p class="tag s{r["score"]}">{tag}</p><p class="why">{html.escape(r["why"])}</p>'
                f'<blockquote>{text}</blockquote><p class="meta">@{html.escape(b["author_username"] or "")} · '
                f'<a href="{html.escape(b["url"] or "")}">open the post</a></p></article>')
    paused_min = round((info["paused_s"] or 0) / 60)
    summary = (f"Gemma read {cnt('ok') + cnt('unclear')} posts overnight and skipped {cnt('link_only')} that were mostly a link. "
               f"{len(picks)} worth your time. " +
               (f"It paused {paused_min} min while the laptop was on battery. " if paused_min else "") +
               (f"{cnt('unclear')} could not be read (answer refused by the check)." if cnt('unclear') else ""))
    PAGE.write_text(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning page · {run}</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:0 auto;padding:24px 16px;background:#faf8f4;color:#1d1b18}}
h1{{font-size:1.4rem;margin:0 0 4px}}.sum{{color:#5c574f;margin:0 0 24px}}article{{background:#fff;border:1px solid #e6e1d8;border-radius:12px;padding:14px 16px;margin:0 0 14px}}
.tag{{font-weight:700;margin:0;font-size:.85rem;text-transform:uppercase;letter-spacing:.04em}}.s3{{color:#b4461f}}.s2{{color:#6b5f2a}}
.why{{margin:6px 0;font-weight:600}}blockquote{{margin:8px 0;padding-left:12px;border-left:3px solid #e6e1d8;color:#3a362f}}.meta{{margin:0;color:#7a746a;font-size:.9rem}}
.none{{color:#5c574f}}</style>
<h1>Your morning page</h1><p class="sum">{html.escape(summary)}</p>
{"".join(card(r) for r in picks) or '<p class="none">Nothing worth your time last night. Go and live your life.</p>'}
""", encoding="utf8")
    return len(picks)

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--until", default="07:00", help="stop (and write the page) at this WAT time")
    ap.add_argument("--fake-power", help="file containing on/off, for tests")
    a = ap.parse_args()
    start = now(); h, m = map(int, a.until.split(":"))
    deadline = start.replace(hour=h, minute=m, second=0, microsecond=0)
    if deadline <= start: deadline += dt.timedelta(days=1)
    run = start.strftime("%Y-%m-%d")
    night = open_night(); profile = get_profile(); items = todo(night, a.limit)
    night.execute("insert or replace into runs(run, started, read, paused_s) values(?,?,0,0)", (run, start.isoformat()))
    night.commit(); log("start", run=run, todo=len(items), until=deadline.isoformat())
    print(f"night shift {run}: {len(items)} new bookmarks, until {deadline:%H:%M} WAT", flush=True)
    paused_total, stopped = 0, "done"
    for i, r in enumerate(items, 1):
        if now() >= deadline: stopped = "until"; break
        p = wait_for_power(deadline, a.fake_power)
        if p is None: stopped = "until_on_battery"; break
        paused_total += p
        t0 = time.time()
        status, score, why, quote, calls, reasons = read_post(profile, r["text"] or "")
        s = round(time.time() - t0, 1)
        night.execute("insert or replace into reads values(?,?,?,?,?,?,?,?,?,?)",
                      (r["id"], run, now().isoformat(), status, score, why, quote, calls, json.dumps(reasons), s))
        night.execute("update runs set read=?, paused_s=? where run=?", (i, paused_total, run)); night.commit()
        print(f"{i:3}/{len(items)} {s:5.1f}s {status:9} {'' if score is None else score}", flush=True)
    night.execute("update runs set ended=?, stopped=?, paused_s=? where run=?", (now().isoformat(), stopped, paused_total, run))
    night.commit()
    n = morning_page(night, run); log("end", run=run, picks=n, stopped=stopped, paused_s=paused_total)
    print(f"done ({stopped}). {n} picks. Morning page: {PAGE}")

if __name__ == "__main__":
    main()
