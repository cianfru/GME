# First ETH funder of each address (earliest inbound value tx, normal then internal) via Blockscout. Cached.
import sys, json, os, time
sys.path.insert(0, os.path.dirname(__file__))
import bs
CF = os.path.join(bs.CACHE, "funders.json")
cache = json.load(open(CF)) if os.path.exists(CF) else {}
def first_funder(a):
    a = a.lower()
    if a in cache: return cache[a]
    best = None
    for path in (f"/addresses/{a}/transactions", f"/addresses/{a}/internal-transactions"):
        # oldest first: page to the end is expensive; Blockscout sorts newest-first, so use filter=to and walk pages
        items = bs.pages(path, {"filter": "to"}, max_pages=30)
        for t in items:
            v = int(t.get("value") or 0)
            if v <= 0: continue
            frm = (t.get("from") or {}).get("hash", "").lower()
            ts = t.get("timestamp")
            if not ts: continue
            if best is None or ts < best["ts"]:
                best = {"funder": frm, "eth": v / 1e18, "ts": ts, "name": (t.get("from") or {}).get("name")}
    cache[a] = best
    json.dump(cache, open(CF, "w"))
    return best
if __name__ == "__main__":
    addrs = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    for a in addrs:
        f = first_funder(a)
        print(a, f and f["funder"], f and round(f["eth"], 4), f and f["ts"][:19], f and f.get("name"))
