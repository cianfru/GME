# Who moved each GME run: net DEX buying by buyer type, the pool's net GME outflow, and what the cluster did.
import sys, json, collections, os, bisect
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
T = load(); pa = prices(); ethp = prices("eth_prices.csv")
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {"0x05391bd57d8c6fb30d9c39f6618f2207893922dc", "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
CL = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
bundle = set(json.load(open(os.path.join(D, "launch_tree.json")))["tree"])
outs = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: outs[s][r] += v
deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(x for k, x in o.items() if k in CEX) / sum(o.values()) >= 0.95}
first = {}
for s, r, ts, v, b in T: first.setdefault(r, ts)
types = json.load(open(os.path.join(D, "addr-types.json")))
W = [("Run 1 · first pump", "2024-05-25", "2024-06-14"), ("Run 2a · ignition", "2024-10-10", "2024-10-31"), ("pause", "2024-11-01", "2024-11-21"),
     ("Run 2b · to the top", "2024-11-21", "2024-12-12"), ("Top & distribution", "2024-12-12", "2025-02-28"), ("Last 12 months", "2025-10-29", "2026-10-29")]
out = []
for name, a, b in W:
    t0, t1 = a + "T00:00:00Z", b + "T23:59:59Z"
    net = collections.defaultdict(float); netusd = collections.defaultdict(float)
    pool = 0.0; cex_dep = collections.Counter(); cex_wd = collections.Counter()
    for s, r, ts, v, bk in T:
        if ts < t0 or ts > t1: continue
        if r == PAIR: pool += v
        if s == PAIR: pool -= v
        p = pa(ts)
        if s in infra and s not in CEX and s not in LP and r not in infra: net[r] += v; netusd[r] += v * p
        if r in infra and r not in CEX and r not in LP and s not in infra: net[s] -= v; netusd[s] -= v * p
        if (r in CEX or r in deplike) and s not in infra and s not in deplike: cex_dep["cl" if s in CL else "other"] += v * p
        if s in CEX and r not in infra and r not in deplike: cex_wd["cl" if r in CL else "other"] += v * p
    cat = collections.Counter(); catn = collections.Counter()
    for w, u in netusd.items():
        if u <= 0: continue
        k = "cluster" if w in CL else ("bundle" if w in bundle else ("new wallet" if first.get(w, "") >= t0 else "existing holder"))
        cat[k] += u; catn[k] += 1
    sells = collections.Counter()
    for w, u in netusd.items():
        if u >= 0: continue
        k = "cluster" if w in CL else ("bundle" if w in bundle else ("new wallet" if first.get(w, "") >= t0 else "existing holder"))
        sells[k] += -u
    pos = sorted(((w, u) for w, u in netusd.items() if u > 0), key=lambda x: -x[1])
    tot = sum(u for w, u in pos)
    p0, p1 = pa(a), pa(b)
    row = dict(name=name, a=a, b=b, p0=p0, p1=p1, mult=p1 / p0, poolOut=-pool, netBuyUsd=tot, netSellUsd=sum(sells.values()), buyers=len(pos), cat=dict(cat), catn=dict(catn), sells=dict(sells),
               top1=pos[0][1] / tot if pos else 0, top10=sum(u for w, u in pos[:10]) / tot if pos else 0, top=[(w, u, w in CL) for w, u in pos[:15]], cexDep=dict(cex_dep), cexWd=dict(cex_wd))
    out.append(row)
    print(f"\n{name} {a}→{b}: mcap ${p0*SUPPLY/1e6:.1f}M → ${p1*SUPPLY/1e6:.1f}M ({p1/p0:.1f}×) · GME out of pool {(-pool)/1e9:+.1f}B")
    print(f"  net buyers {len(pos)}: ${tot:,.0f}  ·  net sellers ${sum(sells.values()):,.0f}")
    print("  net buying by type:", {k: f"${v:,.0f} ({100*v/tot:.0f}%, {catn[k]} wallets)" for k, v in cat.most_common()})
    print("  net selling by type:", {k: f"${v:,.0f}" for k, v in sells.most_common()})
    print(f"  top-1 {100*row['top1']:.0f}% · top-10 {100*row['top10']:.0f}%")
    print("  exchange deposits:", {k: f"${v:,.0f}" for k, v in cex_dep.items()}, " withdrawals:", {k: f"${v:,.0f}" for k, v in cex_wd.items()})
    print("  top net buyers:", [(w[:10], f"${u:,.0f}", "CL" if c else types.get(w)) for w, u, c in row["top"]])
json.dump(out, open(os.path.join(D, "runs.json"), "w"))
open(os.path.join(D, "run_top_buyers.txt"), "w").write("\n".join(sorted({w for row in out[:5] for w, u, c in row["top"] if not c})))
# exchange listing proxies: first GME into each exchange wallet
for a in ("0x9642b23ed1e01df1092b92641051881a322f5d4e", "0x0d0707963952f2fba59dd06f2b425ace40b492fe", "0x8fca4ade3a517133ff23ca55cdaea29c78c990b8", "0xf81b45b1663b7ea8716c74796d99bbe4ea26f488"):
    ts = next((t[2] for t in T if t[1] == a or t[0] == a), None); print("first GME at", EX[a]["name"], ts)
