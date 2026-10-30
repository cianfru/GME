# Refresh the focus wallet's ETH history (normal transactions with value) from Blockscout → data/focus_eth.json.
# Compact: from, to, eth, ts, fromContract, toContract. Only overwrites when the fetch returns at least as many
# transactions as already stored, so a rate-limited or partial fetch never shrinks the file.
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bs
from txlib import FOCUS, D
OUT = os.path.join(D, "focus_eth.json")
def compact(items):
    out = []
    for t in items:
        v = int(t.get("value") or 0)
        if v <= 0: continue
        f, to = t.get("from") or {}, t.get("to") or {}
        out.append(dict(**{"from": (f.get("hash") or "").lower(), "to": (to.get("hash") or "").lower(), "eth": v / 1e18, "ts": t["timestamp"],
                         "fromContract": bool(f.get("is_contract")) and f.get("proxy_type") != "eip7702", "toContract": bool(to.get("is_contract")) and to.get("proxy_type") != "eip7702"}))
    return sorted(out, key=lambda x: x["ts"])
if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else None
    items = json.load(open(src)) if src else bs.pages(f"/addresses/{FOCUS}/transactions", max_pages=200)
    new = compact(items)
    old = json.load(open(OUT)) if os.path.exists(OUT) else []
    if len(new) >= len(old):
        json.dump(new, open(OUT, "w")); print(f"focus_eth.json: {len(new)} value transfers")
    else:
        print(f"fetch returned {len(new)} < stored {len(old)}; keeping the stored file")
