# Market-wide reads: holder counts over time (exact integer balances), and the last 30/90/180 days of DEX flow:
# who is buying, who is selling, and whether the focus cluster is the buyer.
import sys, json, collections, os, csv, datetime
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
pa = prices()
CL = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
raw = collections.defaultdict(int); months = {}; prev = None
TH = [1, 10**6 * 10**9, 10**8 * 10**9, 10**9 * 10**9]   # >0, ≥1M, ≥100M, ≥1B GME
cnt = [0, 0, 0, 0]
def bump(a, old, new):
    if a in infra: return
    for i, t in enumerate(TH):
        cnt[i] += (new >= t) - (old >= t)
rows = []
for r in csv.reader(open(os.path.join(D, "transfers.csv"))):
    if r[0] == "sender": continue
    s, t, ts, v = r[0], r[1], r[2], int(r[3])
    m = ts[:7]
    if prev and m != prev: months[prev] = list(cnt)
    os_, ot = raw[s], raw[t]
    raw[s] -= v; raw[t] += v
    bump(s, os_, raw[s]); bump(t, ot, raw[t])
    prev = m
months[prev] = list(cnt)
print("month    holders  ≥1M   ≥100M  ≥1B GME   (infra excluded)")
for m, c in months.items(): print(m, *[str(x).rjust(6) for x in c])
T = load(); NOW = T[-1][2]
def window(days):
    t0 = (datetime.datetime.fromisoformat(NOW.replace("Z", "")) - datetime.timedelta(days=days)).isoformat() + "Z"
    w = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])  # buy tok, sell tok, buy usd, sell usd
    first_seen = {}
    for s, r, ts, v, b in T:
        first_seen.setdefault(r, ts)
        if ts < t0: continue
        p = pa(ts)
        if s in infra and s not in CEX and r not in infra: w[r][0] += v; w[r][2] += v * p
        if r in infra and r not in CEX and s not in infra: w[s][1] += v; w[s][3] += v * p
    buyers = [a for a, x in w.items() if x[0] > 0]; sellers = [a for a, x in w.items() if x[1] > 0]
    bu = sum(x[2] for x in w.values()); su = sum(x[3] for x in w.values())
    net = sorted(((a, x[0] - x[1], x[2] - x[3]) for a, x in w.items()), key=lambda z: -z[2])
    new = [a for a in buyers if first_seen.get(a, "") >= t0]
    cl_net = sum(x[2] - x[3] for a, x in w.items() if a in CL)
    print(f"\nlast {days}d: {len(buyers)} wallets bought (${bu:,.0f}), {len(sellers)} sold (${su:,.0f}) on DEX · net ${bu-su:+,.0f} · {len(new)} first-time buyers · focus-cluster net ${cl_net:+,.0f}")
    print("  top net buyers:", [(a[:10], f"{n/1e9:.2f}B", f"${u:,.0f}", "CLUSTER" if a in CL else "") for a, n, u in net[:8]])
    print("  top net sellers:", [(a[:10], f"{n/1e9:.2f}B", f"${u:,.0f}", "CLUSTER" if a in CL else "") for a, n, u in net[::-1][:8]])
    top10 = sum(u for a, n, u in net[:10] if u > 0); pos = sum(u for a, n, u in net if u > 0)
    print(f"  top-10 net buyers = {100*top10/pos:.0f}% of all net buying")
    return dict(days=days, buyers=len(buyers), sellers=len(sellers), buyUsd=bu, sellUsd=su, newBuyers=len(new), clusterNet=cl_net,
                topBuyers=[(a, n, u, a in CL) for a, n, u in net[:15]], topSellers=[(a, n, u, a in CL) for a, n, u in net[::-1][:15]])
res = {"holders": months, "windows": [window(d) for d in (30, 90, 180)]}
json.dump(res, open(os.path.join(D, "market.json"), "w"))
