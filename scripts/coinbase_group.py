# The "Coinbase group": every wallet that has sent GME to the collector 0xe1fc…9717 (31 wallets on 30 Oct 2026,
# 28 of them first funded by the same Coinbase withdrawal wallet). Rebuilt each run so new feeders are included;
# funding details from the previous file are kept.
import sys, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
COLLECTOR = "0xe1fc21df6bbe9caa933f93896866501375669717"
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
P = os.path.join(D, "coinbase_group.json")
prev = {r["a"]: r for r in (json.load(open(P)) if os.path.exists(P) else [])}
ins, outs = flows(T, by, COLLECTOR)
rows = []
for a in sorted(ins, key=lambda a: -ins[a][0]):
    if a in infra: continue
    buy = usd = 0.0; nb = 0
    for i in by[a]:
        s, r, ts, v, b = T[i]
        if r == a and s in infra and s not in CEX: buy += v; usd += v * pa(ts); nb += 1
    row = dict(prev.get(a, {})); row.update(a=a, sent=ins[a][0], buy=buy, buyusd=usd, nb=nb, bal=balance_at(T, by, a))
    rows.append(row)
json.dump(rows, open(P, "w"))
print(f"Coinbase group: collector + {len(rows)} feeders; collector holds {balance_at(T, by, COLLECTOR)/1e9:.2f}B")
