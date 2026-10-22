"""Test: can Gemma 4 E2B (Ollama) read frames from a silent saved demo video? Usage: python test_frames.py [n_videos]"""
import base64, json, os, sqlite3, subprocess, sys, time, urllib.request
from pathlib import Path

N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
OUT = Path(__file__).parent / "out"; VID = OUT / "frames_test"; VID.mkdir(parents=True, exist_ok=True)
FFMPEG_DIR = r"C:\Users\DELL\tools\testreel\node_modules\ffmpeg-static"; FFMPEG = os.path.join(FFMPEG_DIR, "ffmpeg.exe")
PY = sys.executable

night = sqlite3.connect(OUT / "night.db"); src = sqlite3.connect(Path.home() / ".bookmark-cli" / "bookmarks.db")
ids = [r[0] for r in night.execute("select id from videos where status='silent' order by at")][:N]
for bid in ids:
    text, url = src.execute("select text, url from bookmarks where id=?", (bid,)).fetchone()
    for f in VID.glob(f"{bid}*"): f.unlink()
    t0 = time.time()
    subprocess.run([PY, "-m", "yt_dlp", "-q", "--no-warnings", "-f", "best[height<=720]/best", "-o", str(VID / f"{bid}.%(ext)s"), url],
                   capture_output=True, text=True, timeout=240)
    vf = next(iter(VID.glob(f"{bid}.*")), None)
    if not vf: print(bid, "download failed"); continue
    dur = float(json.loads(subprocess.run([PY, "-m", "yt_dlp", "-J", "--skip-download", "--no-warnings", url], capture_output=True, text=True).stdout).get("duration") or 10)
    frames = []
    for k in range(4):                                    # 4 frames at 15%, 38%, 62%, 85% of the video, 768 px wide
        fp = VID / f"{bid}_f{k}.jpg"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{dur * (0.15 + 0.233 * k):.2f}", "-i", str(vf),
                        "-frames:v", "1", "-vf", "scale=768:-2", str(fp)], capture_output=True)
        if fp.exists(): frames.append(base64.b64encode(fp.read_bytes()).decode())
    dl_s = round(time.time() - t0, 1)
    prompt = (f'These are {len(frames)} frames from a short silent video that someone shared with this post:\n"""{text[:700]}"""\n'
              'Say only what you can actually see on screen: the product or tool shown, any visible text, code or UI. '
              'Answer with JSON only: {"shown": "one sentence", "visible_text": ["short words you can read on screen"], '
              '"tools": ["names you can read on screen or in the post"]}')
    body = {"model": "gemma4:e2b-it-qat", "stream": False, "think": False, "format": "json",
            "options": {"temperature": 0, "num_predict": 300},
            "messages": [{"role": "user", "content": prompt, "images": frames}]}
    t0 = time.time()
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        out = json.loads(urllib.request.urlopen(req, timeout=600).read())["message"]["content"]
    except Exception as e:
        out = f"ERROR {e}"
    print(f"\n== {url}  ({dur:.0f}s, {len(frames)} frames, download+frames {dl_s}s, gemma {time.time()-t0:.0f}s)")
    print("POST:", " ".join(text.split())[:160]); print("GEMMA:", out)
