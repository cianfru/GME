# Buy-and-forward detector: fresh wallets (first GME in the last 90 days) that bought on a DEX and then sent
# ≥80% of it to one other wallet. Grouped by the receiving ("holding") wallet. Also records who else sent GME
# to each feeder, so a wallet that tops up a feeder is linked to the same operation.
import sys, json, collections, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {"0x05391bd57d8c6fb30d9c39f6618f2207893922dc", "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
NOW = T[-1][2]; t90 = (datetime.datetime.fromisoformat(NOW[:19]) - datetime.timedelta(days=90)).isoformat()
first = {}
for s, r, ts, v, b in T: first.setdefault(r, ts)
vault = collections.defaultdict(lambda: dict(feeders=set(), tok=0.0, usd=0.0, first=None, last=None, sources={}))
for a, t in first.items():
    if a in infra or t < t90: continue
    bought = usd = 0.0; fw = collections.Counter(); src = collections.Counter()
    for i in by[a]:
        s, r, ts, v, b = T[i]
        if r == a and s in infra and s not in CEX and s not in LP: bought += v; usd += v * pa(ts)
        elif r == a and s not in infra: src[s] += v
        if s == a and r not in infra: fw[r] += v
    if bought < 1e7 or not fw: continue
    tgt, amt = fw.most_common(1)[0]
    if amt >= 0.8 * bought:
        x = vault[tgt]; x["feeders"].add(a); x["tok"] += amt; x["usd"] += usd
        t0 = min(T[i][2] for i in by[a]); t1 = max(T[i][2] for i in by[a])
        x["first"] = min(x["first"] or t0, t0); x["last"] = max(x["last"] or t1, t1)
        for k, v in src.items():
            if k != tgt and v >= 0.1 * amt: x["sources"][k] = x["sources"].get(k, 0) + v
# What each holding wallet still holds, and how much of what it got has gone on (to an exchange, or anywhere).
def after(a):
    bal = to_cex = sold = sent = 0.0
    for i in by[a]:
        s, r, ts, v, b = T[i]
        if s == r: continue
        if r == a: bal += v
        if s == a:
            bal -= v; sent += v
            if r in CEX: to_cex += v
            elif r in infra and r not in LP: sold += v
    return dict(bal=max(bal, 0.0), sent=sent, toCex=to_cex, soldDex=sold)
allv = {v: dict(feeders=sorted(x["feeders"]), tok=x["tok"], usd=x["usd"], first=x["first"], last=x["last"], sources=x["sources"], **after(v))
        for v, x in sorted(vault.items(), key=lambda kv: -kv[1]["tok"])}
# A buy-and-forward target only counts as a holding wallet while it keeps the coins: ≥80% of what it received is still
# there and no more than 20% was sold on a DEX or sent to an exchange. The rest bought and then sold or passed the coins
# on (relays); they are not accumulation, so they stay out of the accumulator cohort and the watch groups.
holds = lambda x: x["bal"] >= 0.8 * x["tok"] and x["soldDex"] + x["toCex"] <= 0.2 * x["tok"]
out = {v: x for v, x in allv.items() if holds(x)}
json.dump({v: x for v, x in allv.items() if not holds(x)}, open(os.path.join(D, "vaults90_relays.json"), "w"))
json.dump(out, open(os.path.join(D, "vaults90.json"), "w"))
print(f"{len(out)} holding wallets still holding what fresh buy-and-forward wallets sent them in the last 90 days "
      f"({len(allv) - len(out)} relays that sold or passed it on, to {NOW[:16]})")
