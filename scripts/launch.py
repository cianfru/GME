# The launch: who bought in the first blocks, who funded them, what they paid (exact, from Swap events),
# and what happened to those coins afterwards (sold to the pool / moved / still held).
import sys, json, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); infra = set(EX)
fund = json.load(open(os.path.join(D, "bs", "funders.json")))
lb = json.load(open(os.path.join(D, "early", "launch_buyers.json")))
B0 = 19858497
block0 = sorted(a for a, e in lb.items() if e["first"] == B0)
ethp = prices("eth_prices.csv")
def group(a):
    f = (fund.get(a) or {}).get("funder")
    if a == "0x6b4bed0b3a7bb0c7d4b905cdc7ffc4233d62fdf6" or f == "0x6b4bed0b3a7bb0c7d4b905cdc7ffc4233d62fdf6": return "A"
    if f in ("0x2749c3c33cd4ec2f6d6ef859c05fca980d8a2360", "0x682370291d70f695d7d83403fb83934a2fea4cba"): return "A"
    if f == "0xadee001d258e19874fb67d595af9342d3f8cb999": return "B"
    return "?"
rows = []
for a in block0:
    ins, outs = flows(T, by, a)
    got = sum(e[0] for e in ins.values())
    to_pool = sum(e[0] for k, e in outs.items() if k in infra)
    to_wal = {k: e[0] for k, e in outs.items() if k not in infra}
    # USD of pool sales at the day price (launch week: daily close ~ under-states nothing material after day 3)
    sold_usd = 0.0
    for i in by[a]:
        s, r, ts, v, b = T[i]
        if s == a and r in infra: sold_usd += v * pa(ts)
    last = max(T[i][2] for i in by[a])
    rows.append(dict(a=a, g=group(a), eth=lb[a]["eth"], got=got, toPool=to_pool, toWal=sum(to_wal.values()), walTargets=sorted(to_wal.items(), key=lambda x: -x[1])[:3], bal=balance_at(T, by, a), soldUsd=sold_usd, last=last[:10]))
cost_usd = sum(r["eth"] for r in rows) * ethp("2024-05-13")
tot = lambda k, g=None: sum(r[k] for r in rows if g is None or r["g"] == g)
print(f"launch block {B0}: {len(rows)} wallets, paid {tot('eth'):.3f} ETH (~${cost_usd:,.0f}); received {tot('got')/1e9:.1f}B = {100*tot('got')/SUPPLY:.1f}% of supply")
for g in "AB?":
    n = sum(1 for r in rows if r["g"] == g)
    if n: print(f"  group {g}: {n} wallets · paid {tot('eth', g):.3f} ETH · got {tot('got', g)/1e9:.1f}B · sold to pools {tot('toPool', g)/1e9:.1f}B (${tot('soldUsd', g):,.0f}) · moved to wallets {tot('toWal', g)/1e9:.1f}B · still hold {tot('bal', g)/1e9:.2f}B")
for r in rows:
    print(r["a"][:12], r["g"], f"{r['eth']:.3f}ETH got {r['got']/1e9:.2f}B pool {r['toPool']/1e9:.2f}B (${r['soldUsd']:,.0f}) wal {r['toWal']/1e9:.2f}B bal {r['bal']/1e9:.2f}B last {r['last']}", [(k[:10], round(v/1e9, 2)) for k, v in r["walTargets"]])
json.dump(rows, open(os.path.join(D, "launch_block0.json"), "w"))
