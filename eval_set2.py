"""Score the clean set 2 with the frozen night-shift code (same prompt, rule and guard). Writes out/set2_scores.json."""
import json, sqlite3, time
from pathlib import Path
import nightshift as ns
ids = json.load(open(ns.OUT / "set2_ids.json"))
src = sqlite3.connect(ns.SRC_DB); src.row_factory = sqlite3.Row
profile = ns.get_profile(); res = []
for i, bid in enumerate(ids, 1):
    r = src.execute("select id, text, likes from bookmarks where id=?", (bid,)).fetchone()
    t0 = time.time(); status, score, why, quote, calls, reasons = ns.read_post(profile, r["text"] or "")
    res.append({"n": i, "id": bid, "likes": r["likes"], "status": status, "score": score, "why": why, "calls": calls, "s": round(time.time() - t0, 1)})
    print(f"{i:2}/50 {res[-1]['s']:5.1f}s {status}", flush=True)
json.dump({"profile": profile, "results": res}, open(ns.OUT / "set2_scores.json", "w", encoding="utf8"), indent=1)
print("DONE")
