# Reliable first-ETH-funder lookup (Blockscout Etherscan-compatible API, oldest first), cached, rate-limit aware.
import sys, json, os, time, urllib.parse, urllib.request, concurrent.futures, threading
sys.path.insert(0, os.path.dirname(__file__))
import bs
CACHE = os.path.join(os.path.dirname(__file__), "..", "data", "funders_rel.json")
lock = threading.Lock()
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
def q(params):
    url = "https://eth.blockscout.com/api?" + urllib.parse.urlencode(params)
    for k in range(7):
        try:
            with bs._OP.open(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=60) as r:
                d = json.load(r)
            res = d.get("result")
            if isinstance(res, list): return res
            if "No transactions" in str(d.get("message")) or "No internal" in str(d.get("message")): return []
        except Exception:
            pass
        time.sleep(1.0 * (k + 1))
    return None
def lookup(a):
    if a in cache and cache[a] is not None and not cache[a].get("err"): return a, cache[a]
    best, ok = None, True
    for act in ("txlist", "txlistinternal"):
        res = q({"module": "account", "action": act, "address": a, "sort": "asc", "page": 1, "offset": 25})
        if res is None: ok = False; continue
        for t in res:
            if t.get("to", "").lower() == a and int(t.get("value") or 0) > 0:
                c = {"funder": t["from"].lower(), "eth": int(t["value"]) / 1e18, "ts": int(t["timeStamp"])}
                if best is None or c["ts"] < best["ts"]: best = c
                break
    out = best if best else ({"err": True} if not ok else {"funder": None})
    with lock: cache[a] = out
    return a, out
if __name__ == "__main__":
    addrs = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    done = 0
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        for a, f in ex.map(lookup, addrs):
            done += 1
            if done % 25 == 0:
                with lock: json.dump(cache, open(CACHE, "w"))
                print(done, "done", flush=True)
    json.dump(cache, open(CACHE, "w"))
    print("finished", done, "errors", sum(1 for a in addrs if (cache.get(a) or {}).get("err")), flush=True)
