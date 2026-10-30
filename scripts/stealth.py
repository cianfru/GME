# Stealth-accumulator watchlist: owners who added ≥0.1% of supply in the last 90 days and barely sold.
# Owner = a linked group (all-holder clustering + buy-and-forward vault links + the two known groups) or a single wallet.
# Tags describe HOW they accumulated: fresh wallets forwarding to a holding wallet, exchange withdrawals,
# cross-chain/aggregator buys, many small buys. Behaviour, not identity.
import sys, json, collections, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {"0x05391bd57d8c6fb30d9c39f6618f2207893922dc", "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
BRIDGE = {a for a, v in EX.items() if any(k in (v["name"] or "") for k in ("Relay", "LiFi", "Diamond", "Mayan", "Swift", "Socket", "Rango", "Rubic", "Stargate", "Across", "Bungee"))}
FOC = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
CBG = {r["a"] for r in json.load(open(os.path.join(D, "coinbase_group.json")))} | {"0xe1fc21df6bbe9caa933f93896866501375669717"}
E = json.load(open(os.path.join(D, "entities_all.json")))["entities"]
V = json.load(open(os.path.join(D, "vaults90.json")))
parent = {}
def find(a):
    while parent.get(a, a) != a: parent[a] = parent.get(parent[a], parent[a]); a = parent[a]
    return a
def union(a, b):
    parent.setdefault(a, a); parent.setdefault(b, b); ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb
for e in E:
    ws = e["wallets"]
    if set(ws) & FOC: continue          # the focus group is handled as one known owner
    for a in ws[1:]: union(ws[0], a)
for v, x in V.items():
    for f in x["feeders"]: union(v, f)
    for k in x.get("sources", {}): union(v, k)          # a wallet that tops up a feeder belongs to the same operation
# gas links: a GME holder that paid another watched wallet's ETH (Ethplorer, data/ethplorer_in.json). Exchange and
# bridge funders link no one; dust (<0.001 ETH) is ignored because lookalike "poisoning" addresses send dust.
EP = os.path.join(D, "ethplorer_in.json")
eth_in = json.load(open(EP)) if os.path.exists(EP) else {}
for grp in (FOC, CBG):
    g = sorted(grp)
    for a in g[1:]: union(g[0], a)
# A shared first funder is NOT used as a link: on GME the shared funders turned out to be exchange hot wallets
# and bridge relayers that pay thousands of unrelated people.
labels = {}
import csv
for a, n in csv.reader(open(os.path.join(D, "eth_labels.csv"))): labels[a] = n
for a, d in eth_in.items():
    for ts, f, v in d.get("in", []):
        if v >= 0.001 and f in eth_in and f not in infra and f not in labels and f != a: union(a, f)   # both on the watchlist
own = lambda a: find(a) if a in parent else a
NOW = T[-1][2]; t90 = (datetime.datetime.fromisoformat(NOW[:19]) - datetime.timedelta(days=90)).isoformat(); t14 = (datetime.datetime.fromisoformat(NOW[:19]) - datetime.timedelta(days=14)).isoformat()
bal = collections.defaultdict(float); first = {}
for s, r, ts, v, b in T: bal[s] -= v; bal[r] += v; first.setdefault(r, ts)
A = collections.defaultdict(lambda: dict(buy=0.0, usd=0.0, nb=0, sold=0.0, cexin=0.0, cexout=0.0, xin=0.0, xout=0.0, bridge=0.0, lastbuy="", days=set(), wallets=set()))
for s, r, ts, v, b in T:
    if ts < t90: continue
    p = pa(ts)
    if r not in infra:
        o = own(r); x = A[o]
        if s not in infra and own(s) == o: continue
        x["wallets"].add(r)
        if s in infra and s not in CEX and s not in LP:
            x["buy"] += v; x["usd"] += v * p; x["nb"] += 1; x["lastbuy"] = max(x["lastbuy"], ts); x["days"].add(ts[:10])
            if s in BRIDGE: x["bridge"] += v
        elif s in CEX: x["cexin"] += v
        elif s not in infra: x["xin"] += v
    if s not in infra:
        o = own(s); x = A[o]
        if r not in infra and own(r) == o: continue
        if r in infra and r not in CEX and r not in LP: x["sold"] += v
        elif r in CEX: x["cexout"] += v
        elif r not in infra and r != DEAD: x["xout"] += v
members = collections.defaultdict(set)
for a in list(bal):
    if a not in infra: members[own(a)].add(a)
rows = []
for o, x in A.items():
    net = x["buy"] + x["cexin"] + x["xin"] - x["sold"] - x["cexout"] - x["xout"]
    ws = members.get(o, {o})
    held = sum(max(bal[a], 0) for a in ws)
    if net < 0.001 * SUPPLY: continue
    acquired = x["buy"] + x["cexin"] + x["xin"]
    if x["sold"] + x["cexout"] > 0.15 * acquired: continue      # sold meaningfully → not accumulating
    fs = min(first.get(a, "9") for a in ws)
    vault_fed = sum(len(V[v]["feeders"]) for v in V if own(v) == o)
    tags = []
    if o == own(FOCUS): tags.append("your wallet's cluster")
    elif o == own("0xe1fc21df6bbe9caa933f93896866501375669717"): tags.append("Coinbase group")
    if vault_fed: tags.append(f"{vault_fed} fresh wallet(s) buy→forward")
    if x["cexin"] > 0.2 * acquired: tags.append("exchange withdrawals")
    if x["bridge"] > 0.2 * x["buy"] and x["buy"] > 0: tags.append("cross-chain/aggregator buys")
    if x["nb"] >= 10: tags.append(f"{x['nb']} small buys")
    if fs >= t90: tags.append("new to GME")
    if len(ws) > 1 and not vault_fed and "cluster" not in " ".join(tags) and "Coinbase" not in " ".join(tags): tags.append(f"{len(ws)} linked wallets")
    rows.append(dict(owner=o, wallets=sorted(ws, key=lambda a: -bal[a]), n=len(ws), net=net, pct=100 * net / SUPPLY, held=held, heldPct=100 * held / SUPPLY,
                     usd=x["usd"], buys=x["nb"], buyDays=len(x["days"]), avgBuyUsd=x["usd"] / x["nb"] if x["nb"] else 0, avgPrice=x["usd"] / x["buy"] if x["buy"] else None,
                     cexin=x["cexin"], xin=x["xin"], sold=x["sold"] + x["cexout"], lastBuy=x["lastbuy"][:10], active=x["lastbuy"] >= t14, first=fs[:10], tags=tags))
rows.sort(key=lambda r: -r["net"])
json.dump(dict(asOf=NOW, rows=rows), open(os.path.join(D, "stealth.json"), "w"))
# wallets worth an ETH-funding lookup on the next run (watched owners outside the two big groups + vault feeders)
watch = set()
for r in rows:
    if r["n"] <= 20: watch.update(r["wallets"])
for v, x in V.items(): watch.add(v); watch.update(x["feeders"])
open(os.path.join(D, "watch_addrs.txt"), "w").write("\n".join(sorted(watch)))
print(f"as of {NOW}: {len(rows)} owners added ≥0.1% of supply in 90 days while selling <15% of what they took in")
print(f"together +{sum(r['net'] for r in rows)/1e9:.1f}B ({sum(r['pct'] for r in rows):.1f}% of supply), DEX spend ${sum(r['usd'] for r in rows):,.0f}")
for r in rows:
    top = r["wallets"][0]
    print(f"{top}  n={r['n']:2d}  +{r['net']/1e9:5.2f}B ({r['pct']:.2f}%)  holds {r['held']/1e9:5.2f}B ({r['heldPct']:.2f}%)  spent ${r['usd']:>7,.0f} in {r['buys']:3d} buys/{r['buyDays']:2d} days  avg ${r['avgBuyUsd']:,.0f}  last {r['lastBuy']} {'ACTIVE' if r['active'] else ''}  first {r['first']}  | {'; '.join(r['tags'])}")
