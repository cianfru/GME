# Follow the launch bundle's coins: group-A wallets each forwarded their buy to ONE fresh wallet the same day.
# Trace those second-hop wallets (and any further hops) until the coins hit a pool/exchange or stop.
import sys, json, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); infra = set(EX)
CEX = {a for a, v in EX.items() if v["kind"] == "cex"}
rows = json.load(open(os.path.join(D, "launch_block0.json")))
# Exact ETH proceeds for pool sells during the launch window (from Swap events + tx hashes)
L = json.load(open(os.path.join(D, "early", "launch.json")))
def ad(t): return "0x" + t[-40:]
ethout = collections.defaultdict(float)
sells = collections.defaultdict(float)
swap_by_tx = collections.defaultdict(list)
for s in L["swaps"]:
    h = s["data"][2:]; a0i, a1i, a0o, a1o = [int(h[i*64:(i+1)*64], 16) for i in range(4)]
    swap_by_tx[s["transactionHash"]].append((a0o / 1e18, a1i / 1e9))
for t in L["transfers"]:
    f, r = ad(t["topics"][1]), ad(t["topics"][2])
    if r == PAIR and t["transactionHash"] in swap_by_tx:
        eth = sum(x[0] for x in swap_by_tx[t["transactionHash"]])
        ethout[f] += eth
ethp = prices("eth_prices.csv")
# Track descendants: start at the bundle wallets; follow transfers to non-infra wallets
start = {r["a"] for r in rows}
desc = {}  # addr -> hop
frontier = set(start)
for a in start: desc[a] = 0
hop = 0
while frontier and hop < 4:
    nxt = set()
    for a in frontier:
        ins, outs = flows(T, by, a)
        for k, e in outs.items():
            if k in infra or k in desc: continue
            # only follow meaningful forwards (≥ 25% of what a received)
            got = sum(x[0] for x in ins.values()) or 1
            if e[0] >= 0.25 * got:
                desc[k] = hop + 1; nxt.add(k)
    frontier = nxt; hop += 1
tree = [a for a in desc if desc[a] > 0]
print(f"bundle descendants: {len(tree)} wallets over {hop} hops")
agg = collections.Counter()
by_month = collections.defaultdict(float)
for a in list(desc):
    for i in by[a]:
        s, r, ts, v, b = T[i]
        if s == a and r in infra and r not in CEX: agg["pool"] += v; agg["pool_usd"] += v * pa(ts); by_month[ts[:7]] += v
        if s == a and r in CEX: agg["cex"] += v; agg["cex_usd"] += v * pa(ts)
    agg["bal"] += balance_at(T, by, a)
print(f"bundle + descendants sold to pools {agg['pool']/1e9:.1f}B (~${agg['pool_usd']:,.0f} at day close), sent to exchanges {agg['cex']/1e9:.1f}B (~${agg['cex_usd']:,.0f}), still hold {agg['bal']/1e9:.2f}B ({100*agg['bal']/SUPPLY:.2f}% of supply)")
print("pool sales by month:", {m: round(v/1e9, 1) for m, v in sorted(by_month.items())})
exact = sum(ethout[a] for a in desc)
print(f"exact ETH from pool sells inside the launch window (first ~27h): {exact:.2f} ETH (~${exact*ethp('2024-05-13'):,.0f})")
holders_now = sorted(((a, balance_at(T, by, a)) for a in desc), key=lambda x: -x[1])[:10]
print("largest current holders in the bundle tree:", [(a[:10], round(b/1e9, 2), desc[a]) for a, b in holders_now if b > 1e6])
# does the bundle tree touch the focus cluster?
fc = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
print("overlap with focus cluster:", [a for a in desc if a in fc])
links = []
for a in desc:
    ins, outs = flows(T, by, a)
    for k, e in list(ins.items()) + list(outs.items()):
        if k in fc: links.append((a[:10], k[:10], round(e[0]/1e9, 3), e[2]))
print("direct transfers bundle-tree <-> focus cluster:", links[:20])
json.dump({"tree": desc, "agg": agg}, open(os.path.join(D, "launch_tree.json"), "w"))
