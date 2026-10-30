# FIFO cost basis per holder (the focus cluster treated as one owner), then:
#  (a) the break-even map: how much held GME has a cost basis at each multiple of today's price
#  (b) who sold during GME's recent bounces: at a loss (underwater sellers getting out) or at a profit
# Lots are priced at the DeFiLlama daily close on the day they arrive (engine convention); a transfer from
# another wallet enters at market, except moves inside the cluster, which keep their lots.
import sys, json, collections, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
T = load(); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
CL = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
LP = {"0x05391bd57d8c6fb30d9c39f6618f2207893922dc", "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
outs = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: outs[s][r] += v
deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(x for k, x in o.items() if k in CEX) / sum(o.values()) >= 0.95}
ent = lambda a: "CLUSTER" if a in CL else a
lots = collections.defaultdict(collections.deque)   # owner -> deque [qty, price, ts]
sales = []   # (ts, owner, qty, cost, price, kind, ageDays)
def pop(o, q):
    dq = lots[o]; got = []
    while q > 1e-6 and dq:
        L = dq[0]
        take = min(q, L[0]); got.append((take, L[1], L[2])); L[0] -= take; q -= take
        if L[0] <= 1e-6: dq.popleft()
    return got
for s, r, ts, v, b in T:
    p = pa(ts); es, er = ent(s), ent(r)
    s_person = s not in infra and s not in deplike
    r_person = r not in infra and r not in deplike
    if s_person and r_person and es == er:
        continue   # inside one owner: lots stay
    taken = pop(es, v) if s_person else []
    if s_person and not r_person and r not in LP and r != DEAD:
        kind = "cex" if (r in CEX or r in deplike) else "dex"
        cost = sum(q * c for q, c, t in taken); qty = sum(q for q, c, t in taken)
        if qty > 0:
            age = sum(q * (datetime.datetime.fromisoformat(ts[:19]) - datetime.datetime.fromisoformat(t[:19])).days for q, c, t in taken) / qty
            sales.append((ts, es, qty, cost, p, kind, age))
    if r_person:
        if s_person and r in CL and s in CL: lots[er].extend([list(x) for x in taken])
        else: lots[er].append([v, p, ts])
P = 5.56e-6
held = [(o, q, c, t) for o, dq in lots.items() for q, c, t in dq if q > 1e-6]
H = sum(q for o, q, c, t in held)
print(f"held by people: {H/1e9:.1f}B · price ${P:.2e} (mcap ${P*SUPPLY/1e6:.1f}M)")
bands = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 10), (10, 20), (20, 1e9)]
res = {"held": H, "bands": []}
print("cost basis vs today      all (B, %)         cluster (B)   others (B)   wallets(others)")
for lo, hi in bands:
    sel = [(o, q) for o, q, c, t in held if lo <= c / P < hi]
    a = sum(q for o, q in sel); cl = sum(q for o, q in sel if o == "CLUSTER"); ot = a - cl
    nw = len({o for o, q in sel if o != "CLUSTER"})
    lab = f"{lo}–{hi}×" if hi < 1e9 else f">{lo}×"
    print(f"{lab:10s} (${lo*P*SUPPLY/1e6:5.1f}M–{'$%.1fM' % (hi*P*SUPPLY/1e6) if hi<1e9 else '   up'})  {a/1e9:7.1f}B {100*a/H:5.1f}%   {cl/1e9:8.1f}   {ot/1e9:8.1f}   {nw}")
    res["bands"].append(dict(lo=lo, hi=hi, all=a, cl=cl, ot=ot, wallets=nw))
# cumulative: supply at break-even or better at each multiple
cum = []
for m in (1.5, 2, 3, 5, 10, 20):
    a = sum(q for o, q, c, t in held if c <= m * P); ot = sum(q for o, q, c, t in held if c <= m * P and o != "CLUSTER")
    cum.append((m, a, ot)); print(f"at {m}× (${m*P*SUPPLY/1e6:.1f}M mcap): {a/1e9:.1f}B ({100*a/H:.0f}%) of held GME is at or above break-even; excluding the cluster {ot/1e9:.1f}B")
res["cum"] = cum
cl_cost = sum(q * c for o, q, c, t in held if o == "CLUSTER") / max(1, sum(q for o, q, c, t in held if o == "CLUSTER"))
print(f"cluster FIFO cost basis of what it holds: ${cl_cost:.2e} ({cl_cost/P:.1f}× today)")
json.dump(res, open(os.path.join(D, "overhang.json"), "w"))
json.dump(sales, open(os.path.join(D, "sales.json"), "w"))
