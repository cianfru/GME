# First inbound ETH (normal, then internal) per address via Blockscout's Etherscan-compatible API, oldest first.
import sys, json, os, concurrent.futures, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
import bs

def q(params):
    url = "https://eth.blockscout.com/api?" + urllib.parse.urlencode(params)
    for _ in range(5):
        try:
            with bs._OP.open(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=60) as r:
                return json.load(r).get("result") or []
        except Exception:
            pass
    return []

def first_in(a):
    best = None
    for act in ("txlist", "txlistinternal"):
        for t in q({"module": "account", "action": act, "address": a, "sort": "asc", "page": 1, "offset": 25}):
            if t.get("to", "").lower() == a and int(t.get("value") or 0) > 0:
                c = {"funder": t["from"].lower(), "eth": int(t["value"]) / 1e18, "ts": t["timeStamp"], "kind": act}
                if best is None or int(c["ts"]) < int(best["ts"]):
                    best = c
                break
    return a, best

if __name__ == "__main__":
    addrs = [l.strip() for l in open(sys.argv[1]) if l.strip()]
    out = {}
    with concurrent.futures.ThreadPoolExecutor(6) as ex:
        for a, f in ex.map(first_in, addrs):
            out[a] = f
    json.dump(out, open(sys.argv[2], "w"))
    print(len(out), "resolved", sum(1 for v in out.values() if v))
