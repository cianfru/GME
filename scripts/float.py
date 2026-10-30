# Supply accounting + who accumulated in the last 90 days, by OWNER (groups merged).
import sys, json, collections, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {"0x05391bd57d8c6fb30d9c39f6618f2207893922dc", "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
FOC = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
CBG = {r["a"] for r in json.load(open(os.path.join(D, "coinbase_group.json")))} | {"0xe1fc21df6bbe9caa933f93896866501375669717"}
E = json.load(open(os.path.join(D, "entities_all.json")))["entities"]
owner = {}
for a in FOC: owner[a] = "FOCUS"
for a in CBG: owner[a] = "COINBASE"
for i, e in enumerate(E):
    ws = set(e["wallets"])
    if ws & FOC:      # the loose extension of the focus group: keep separate as "FOCUS+" (upper bound)
        for a in ws - FOC: owner.setdefault(a, "FOCUS_EXT")
        continue
    if ws & CBG:
        for a in ws: owner.setdefault(a, "COINBASE")
        continue
    for a in ws: owner.setdefault(a, f"G{i}")
NOW = T[-1][2]
t90 = (datetime.datetime.fromisoformat(NOW[:19]) - datetime.timedelta(days=90)).isoformat()
t365 = (datetime.datetime.fromisoformat(NOW[:19]) - datetime.timedelta(days=365)).isoformat()
bal = collections.defaultdict(float); last = {}; firstseen = {}
for s, r, ts, v, b in T:
    bal[s] -= v; bal[r] += v; last[s] = ts; last[r] = ts; firstseen.setdefault(r, ts)
cat = collections.Counter()
for a, b in bal.items():
    if b <= 0: continue
    if a == DEAD: cat["Burned"] += b
    elif a == PAIR: cat["Uniswap V2 pool"] += b
    elif a in infra: cat["Exchanges, other pools & contracts"] += b
    elif owner.get(a) == "FOCUS": cat["Your wallet's cluster (69)"] += b
    elif owner.get(a) == "FOCUS_EXT": cat["Its looser extension (88 more)"] += b
    elif owner.get(a) == "COINBASE": cat["Coinbase group (31)"] += b
    elif a in owner: cat["Other multi-wallet groups"] += b
    else:
        if b < 1e8: cat["Small wallets (<100M GME)"] += b
        elif last[a] < t365: cat["Independent, untouched >1 year"] += b
        elif last[a] < t90: cat["Independent, quiet 3–12 months"] += b
        else: cat["Independent, active last 90 days"] += b
print(f"as of {NOW}")
order = ["Burned", "Uniswap V2 pool", "Exchanges, other pools & contracts", "Your wallet's cluster (69)", "Its looser extension (88 more)", "Coinbase group (31)", "Other multi-wallet groups",
         "Independent, untouched >1 year", "Independent, quiet 3–12 months", "Independent, active last 90 days", "Small wallets (<100M GME)"]
for k in order: print(f"  {k:40s} {cat[k]/1e9:7.2f}B  {100*cat[k]/SUPPLY:5.1f}%")
print("  total", round(sum(cat.values()) / 1e9, 2))
json.dump({k: cat[k] for k in order}, open(os.path.join(D, "float.json"), "w"))
# ---- 90-day accumulation by owner
def own(a): return owner.get(a, a)
acc = collections.defaultdict(lambda: dict(dex=0.0, dexusd=0.0, cexin=0.0, xin=0.0, xout=0.0, sold=0.0, cexout=0.0, wallets=set(), first=None, n=0))
for s, r, ts, v, b in T:
    if ts < t90: continue
    p = pa(ts)
    for a, sign in ((r, 1), (s, -1)):
        if a in infra: continue
        o = own(a); other = s if sign > 0 else r
        if own(other) == o and other not in infra: continue
        x = acc[o]; x["wallets"].add(a)
        if sign > 0:
            if other in infra and other not in CEX and other not in LP: x["dex"] += v; x["dexusd"] += v * p; x["n"] += 1
            elif other in CEX: x["cexin"] += v
            else: x["xin"] += v
        else:
            if other in infra and other not in CEX and other not in LP: x["sold"] += v; x["dexusd"] -= v * p
            elif other in CEX: x["cexout"] += v
            else: x["xout"] += v
rows = []
for o, x in acc.items():
    net = x["dex"] + x["cexin"] + x["xin"] - x["sold"] - x["cexout"] - x["xout"]
    ws = [a for a in bal if own(a) == o] if o.startswith(("G", "FOCUS", "COINBASE")) else [o]
    held = sum(max(bal[a], 0) for a in ws)
    fs = min(firstseen.get(a, "9") for a in ws)
    rows.append(dict(owner=o, net=net, dexNet=x["dex"] - x["sold"], dexUsd=x["dexusd"], cexNet=x["cexin"] - x["cexout"], xNet=x["xin"] - x["xout"], held=held, wallets=len(ws), first=fs[:10], buys=x["n"]))
rows.sort(key=lambda r: -r["net"])
print("\nTop accumulators, last 90 days (owner = a group or a single wallet):")
print("owner                                         wallets  net 90d   of which DEX ($)        exch.   transfers   holds now   first GME")
for r in rows[:25]:
    print(f"{r['owner'][:44]:44s} {r['wallets']:5d}  {r['net']/1e9:+6.2f}B  {r['dexNet']/1e9:+6.2f}B (${r['dexUsd']:>8,.0f})  {r['cexNet']/1e9:+5.2f}B  {r['xNet']/1e9:+6.2f}B   {r['held']/1e9:6.2f}B   {r['first']}  buys {r['buys']}")
json.dump(rows[:200], open(os.path.join(D, "acc90.json"), "w"))
tot_net_buy = sum(r["dexNet"] for r in rows if r["dexNet"] > 0)
print(f"\nall net DEX buying (owners net positive): {tot_net_buy/1e9:.2f}B; top-10 owners {100*sum(r['dexNet'] for r in sorted(rows, key=lambda r:-r['dexNet'])[:10])/tot_net_buy:.0f}%")
