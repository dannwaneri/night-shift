"""Builds out/review.html: up to 10 notes (half from speech, half read from the screen) to check once against the real video.
The answers box gives a line to paste back, e.g. "1y 2n 3y". Usage: python review.py [n]"""
import html, json, random, sqlite3, sys
from pathlib import Path

OUT = Path(__file__).parent / "out"; N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
night = sqlite3.connect(OUT / "night.db"); night.row_factory = sqlite3.Row
src = sqlite3.connect(Path.home() / ".bookmark-cli" / "bookmarks.db"); src.row_factory = sqlite3.Row
rows = night.execute("select * from videos where status='ok'").fetchall()
screen = [r for r in rows if json.loads(r["notes"]).get("source") == "screen"]
speech = [r for r in rows if json.loads(r["notes"]).get("source") != "screen"]
random.seed(23)                                   # fixed seed: the sample is chosen once, not re-rolled
pick = random.sample(speech, min(len(speech), N - min(len(screen), N // 2))) + random.sample(screen, min(len(screen), N // 2))
random.shuffle(pick)
(OUT / "review_ids.json").write_text(json.dumps([r["id"] for r in pick]))
e = html.escape; cards = []
for i, r in enumerate(pick, 1):
    n = json.loads(r["notes"]); b = src.execute("select text, url, author_username from bookmarks where id=?", (r["id"],)).fetchone()
    if n.get("source") == "screen":
        imgs = "".join(f'<img src="frames/{e(r["id"])}_{k}.jpg">' for k in range(4) if (OUT / "frames" / f"{r['id']}_{k}.jpg").exists())
        seen = "".join(f"<li>{e(x)}</li>" for x in n.get("visible_text") or [])
        check = (f'<p class="how">Silent video. Gemma saw these 4 frames. Does the note match them?</p><div class="frames">{imgs}</div>'
                 f'<ul>{seen}</ul>')
    else:
        check = (f'<p class="how">Spoken video, {round(r["duration"] or 0)} s. Play it (1.5x is fine) and check the note.</p>'
                 f'<blockquote>“{e(n["quote"])}”</blockquote><details><summary>transcript</summary><p>{e(r["transcript"] or "")}</p></details>')
    fixes = "".join(f'<li>heard “{e(f["heard"])}” → {e(f["means"])}</li>' for f in n.get("fixes") or [])
    cards.append(f'''<article data-n="{i}"><p class="num">{i} · @{e(b["author_username"] or "")} · <a href="{e(b["url"])}" target="_blank">open the video</a></p>
<p class="claim">{e(n["claim"])}</p><p class="tools">{" · ".join(e(t) for t in n["tools"])}</p>{f"<ul class=fix>{fixes}</ul>" if fixes else ""}
{check}<div class="btns"><button data-v="y">Accurate</button><button data-v="n">Not accurate</button></div></article>''')
(OUT / "review.html").write_text(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Check the notes once</title><style>body{{font:16px/1.5 system-ui,sans-serif;max-width:720px;margin:0 auto;padding:20px 16px 120px;background:#f6f7f9;color:#16181d}}
article{{background:#fff;border:1px solid #e1e4ea;border-radius:12px;padding:14px 16px;margin:0 0 16px}}.num{{margin:0;color:#6a7280;font-size:.9rem}}
.claim{{font-weight:650;margin:6px 0}}.tools{{color:#1d4ed8;margin:4px 0}}.how{{color:#555b66;font-size:.92rem;margin:8px 0 4px}}
.frames{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}}.frames img{{width:100%;border-radius:6px}}
blockquote{{margin:6px 0;padding-left:12px;border-left:3px solid #d5dae3}}.fix{{color:#555b66;font-size:.92rem}}
.btns button{{font:inherit;padding:8px 14px;margin:8px 8px 0 0;border-radius:8px;border:1px solid #c9ced8;background:#fff;cursor:pointer}}
.btns button.on[data-v=y]{{background:#dcfce7;border-color:#16a34a}}.btns button.on[data-v=n]{{background:#fee2e2;border-color:#dc2626}}
#ans{{position:fixed;left:0;right:0;bottom:0;background:#16181d;color:#fff;padding:12px 16px calc(12px + env(safe-area-inset-bottom,0px));font-family:monospace}}</style>
<h1>Check the notes once</h1><p>Watch once so you never have to again. Mark each note against the real video.</p>
{"".join(cards)}<div id="ans">Answers: <span id="out">none yet</span></div>
<script>const a={{}};document.querySelectorAll("article").forEach(c=>c.querySelectorAll("button").forEach(b=>b.onclick=()=>{{
c.querySelectorAll("button").forEach(x=>x.classList.remove("on"));b.classList.add("on");a[c.dataset.n]=b.dataset.v;
document.getElementById("out").textContent=Object.keys(a).sort((x,y)=>x-y).map(k=>k+a[k]).join(" ");}}));</script>""", encoding="utf8")
print(f"review.html: {len(pick)} notes ({sum(1 for r in pick if json.loads(r['notes']).get('source') == 'screen')} from the screen)")
