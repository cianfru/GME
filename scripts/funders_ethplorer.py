# ETH funding sources (all inbound ETH, oldest first) via Ethplorer's free API — last 50 ETH txs per address.
import sys, json, os, time, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
import bs
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "ethplorer_in.json")
cache = json.load(open(OUT)) if os.path.exists(OUT) else {}
def get(a):
    url = f"https://api.ethplorer.io/getAddressTransactions/{a}?apiKey=freekey&limit=50"
    for k in range(5):
        try:
            with bs._OP.open(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=40) as r:
                d = json.load(r)
            if isinstance(d, list): return d
        except Exception:
            pass
        time.sleep(2 + 2 * k)
    return None
addrs = [l.strip().lower() for l in open(sys.argv[1]) if l.strip()]
for a in addrs:
    if a in cache: continue
    d = get(a)
    if d is None: print("fail", a, flush=True); continue
    ins = sorted([(t["timestamp"], t["from"].lower(), t["value"]) for t in d if t.get("to", "").lower() == a and t.get("value", 0) > 0 and t.get("success", True)])
    outs = sorted([(t["timestamp"], t["to"].lower(), t["value"]) for t in d if t.get("from", "").lower() == a and t.get("value", 0) > 0])
    cache[a] = {"in": ins, "out": outs, "n": len(d)}
    json.dump(cache, open(OUT, "w"))
    time.sleep(0.7)
print("done", len(cache), flush=True)
