"""Feasibility: can the night shift 'watch' my saved short videos? (yt-dlp metadata + audio, Whisper small on CPU)
Usage: python test_video.py [n_candidates] [max_seconds]
"""
import json, os, re, sqlite3, subprocess, sys, time
from pathlib import Path

N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
MAX_S = int(sys.argv[2]) if len(sys.argv) > 2 else 90
OUT = Path(__file__).parent / "out"; AUD = OUT / "audio"; AUD.mkdir(parents=True, exist_ok=True)
FFMPEG_DIR = r"C:\Users\DELL\tools\testreel\node_modules\ffmpeg-static"
os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ["PATH"]
PY = sys.executable

src = sqlite3.connect(Path.home() / ".bookmark-cli" / "bookmarks.db"); src.row_factory = sqlite3.Row
rows = src.execute("select id, text, url, author_username, media_json from bookmarks where source='bookmark' "
                   "order by bookmark_added_at desc, created_at desc limit 200").fetchall()
TECH = re.compile(r"\b(ai|llm|llms|agent|agents|agentic|model|models|gpt|claude|gemini|gemma|llama|qwen|code|coding|coder|python|javascript|typescript|rust|api|gpu|cuda|vram|inference|fine-?tun\w*|rag|mcp|cursor|copilot|open[- ]?source|github|repo|demo|tutorial|benchmark|prompt\w*|token\w*|deploy\w*|cloudflare|workers?|database|sql|tech|engineer\w*|developer|dev|startup|robot\w*|automat\w*)\b", re.I)
if os.environ.get("TECH_ONLY"):   # all saved videos whose post text has technical words, newest first
    rows = src.execute("select id, text, url, author_username, media_json from bookmarks where source='bookmark' "
                       "and media_json like '%\"video\"%' order by created_at desc").fetchall()
    rows = [r for r in rows if TECH.search(r["text"] or "")]
vids = [r for r in rows if '"video"' in (r["media_json"] or "")][:N]

def meta(url):
    p = subprocess.run([PY, "-m", "yt_dlp", "-J", "--no-warnings", "--skip-download", url], capture_output=True, text=True, timeout=90)
    if p.returncode: return None, (p.stderr.strip().splitlines() or ["?"])[-1][:140]
    j = json.loads(p.stdout); e = (j.get("entries") or [j])[0]
    return e.get("duration"), None

import whisper
t0 = time.time(); model = whisper.load_model("small", device="cpu"); print(f"whisper small loaded in {time.time()-t0:.0f}s", flush=True)
res = []
for i, r in enumerate(vids, 1):
    row = {"n": i, "id": r["id"], "url": r["url"], "author": r["author_username"]}
    t = time.time(); dur, err = meta(r["url"]); row["meta_s"] = round(time.time() - t, 1)
    row["duration"] = dur
    if err: row["status"] = "meta_failed: " + err
    elif dur is None: row["status"] = "no_duration"
    elif dur > MAX_S: row["status"] = f"too_long ({dur:.0f}s)"
    else:
        # No conversion step (it needs ffprobe, which the bundled ffmpeg lacks); Whisper decodes the audio file itself.
        t = time.time()
        p = subprocess.run([PY, "-m", "yt_dlp", "-q", "--no-warnings", "-f", "bestaudio/best",
                            "--ffmpeg-location", FFMPEG_DIR, "-o", str(AUD / f"{r['id']}.%(ext)s"), r["url"]],
                           capture_output=True, text=True, timeout=180)
        row["dl_s"] = round(time.time() - t, 1)
        f = next(iter(sorted(AUD.glob(f"{r['id']}.*"))), None)
        if p.returncode or not f:
            row["status"] = "download_failed: " + ((p.stderr.strip().splitlines() or ["?"])[-1][:140])
        else:
            t = time.time()
            try:
                tr = model.transcribe(str(f), fp16=False)
                txt = tr["text"].strip(); row.update(status="ok", lang=tr.get("language"), words=len(txt.split()), transcript=txt[:600])
            except Exception as e:      # e.g. a clip with no sound track at all ("does not contain any stream")
                row["status"] = "no_audio" if "does not contain any stream" in str(e) else "asr_failed: " + str(e)[-120:]
            row["asr_s"] = round(time.time() - t, 1)
    res.append(row)
    print(f"{i:2}/{len(vids)} {row['status'][:40]:40} dur={dur} dl={row.get('dl_s')} asr={row.get('asr_s')} words={row.get('words')} lang={row.get('lang')}", flush=True)
(OUT / "test_video.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf8")
ok = [x for x in res if x["status"] == "ok"]
print(f"\nDONE: {len(ok)}/{len(res)} transcribed (<= {MAX_S}s) | speech (>=10 words): {sum(1 for x in ok if x['words'] >= 10)} "
      f"| median asr {sorted(x['asr_s'] for x in ok)[len(ok)//2] if ok else '-'}s")
