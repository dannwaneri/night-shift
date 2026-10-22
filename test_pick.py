"""Quick test: can local Gemma 4 E2B pick the bookmarks worth reading for what I am writing now?

Reads the 50 newest real bookmarks (source='bookmark') from bookmark-cli's SQLite DB, builds a profile from my
latest DEV posts (fetched live), and asks Gemma (Ollama, temperature 0) for a 0-3 score, one-line reason and an
exact quote from the post. A guard checks every answer; one retry, then "unclear". No open-ended loops.
Usage: python test_pick.py [n]
"""
import json, re, sqlite3, sys, time, urllib.request
from pathlib import Path

N = int(sys.argv[1]) if len(sys.argv) > 1 else 50
MODEL = "gemma4:e2b-it-qat"
DB = Path.home() / ".bookmark-cli" / "bookmarks.db"
OUT = Path(__file__).parent / "out"; OUT.mkdir(exist_ok=True)

def http_json(url, body=None, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "night-shift-test"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

# ---- profile: what I am writing now (my last 6 DEV posts, live) ----
posts = http_json("https://dev.to/api/articles?username=dannwaneri&per_page=6")
profile = "\n".join(f"- {p['title']}: {(p.get('description') or '')[:160]}" for p in posts)

# ---- the 50 newest real bookmarks ----
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
rows = con.execute("select id, text, author_username, url, likes from bookmarks where source='bookmark' "
                   "order by bookmark_added_at desc, created_at desc limit ?", (N,)).fetchall()

PROMPT = """You help me decide which saved posts are worth reading today.

What I am writing about now (my latest posts):
{profile}

A post I saved:
\"\"\"{text}\"\"\"

Score how useful this post is for what I am writing now:
0 = not related, 1 = loosely related, 2 = useful, 3 = read it today.
Answer with JSON only: {{"score": 0-3, "why": "one short sentence", "quote": "a few exact words copied from the post"}}{retry}"""

norm = lambda s: re.sub(r"\s+", " ", s or "").strip().lower()

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

def ask(text, retry_reasons):
    retry = f"\nYour last answer was refused because: {', '.join(retry_reasons)}. Fix only that." if retry_reasons else ""
    body = {"model": MODEL, "stream": False, "think": False, "format": "json",
            "options": {"temperature": 0, "num_predict": 120},
            "messages": [{"role": "user", "content": PROMPT.format(profile=profile, text=text[:900], retry=retry)}]}
    return http_json("http://127.0.0.1:11434/api/chat", body)["message"]["content"]

results = []
t_all = time.time()
for i, r in enumerate(rows, 1):
    text = r["text"] or ""
    t0 = time.time(); reasons = []; v = None; raws = []
    for attempt in range(2):                      # one retry, then unclear
        raw = ask(text, reasons); raws.append(raw)
        v, reasons = guard(raw, text)
        if v: break
    s = round(time.time() - t0, 1)
    results.append({"id": r["id"], "url": r["url"], "author": r["author_username"], "likes": r["likes"],
                    "text": text[:280], "score": v["score"] if v else None, "why": v["why"] if v else None,
                    "quote": v["quote"] if v else None, "status": "ok" if v else "unclear",
                    "calls": len(raws), "reasons": reasons, "s": s})
    print(f"{i:2}/{len(rows)} {s:5.1f}s score={results[-1]['score']} {results[-1]['status']}", flush=True)

(OUT / "test_pick.json").write_text(json.dumps({"profile": profile, "model": MODEL, "results": results}, indent=1), encoding="utf8")
ok = [x for x in results if x["status"] == "ok"]
dist = {k: sum(1 for x in ok if x["score"] == k) for k in range(4)}
times = sorted(x["s"] for x in results)
print(f"\nDONE {len(results)} in {round(time.time()-t_all)}s | guard ok {len(ok)}/{len(results)} | retried {sum(1 for x in results if x['calls']>1)} "
      f"| scores {dist} | median {times[len(times)//2]}s")
