# The focus wallet's cluster treated as ONE owner: only flows crossing the cluster boundary count.
# Classes: DEX buy / DEX sell (pools + routers + aggregators), CEX withdraw / CEX deposit (incl. deposit addresses),
# LP (Uniswap V3 pool / positions), burn, wallet in / wallet out (other people). USD at the day's close.
import sys, json, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
CL = json.load(open(os.path.join(D, "focus_cluster.json")))
who = sys.argv[1] if len(sys.argv) > 1 else "cluster"
mem = {FOCUS} if who == "focus" else {m["a"] for m in CL["members"]}
dep = set(CL["deposits"])
# any deposit-like address (≥95% to CEX) counts as CEX deposit for flow classification
outs = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: outs[s][r] += v
deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(v for k, v in o.items() if k in CEX) / sum(o.values()) >= 0.95}
LP = {"0x05391bd57d8c6fb30d9c39f6618f2207893922dc", "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
def cls(x, incoming):
    if x in LP: return "lp"
    if x == DEAD: return "burn"
    if x in CEX or x in deplike: return "cex"
    if x in infra: return "dex"
    return "wallet"
M = collections.defaultdict(lambda: collections.defaultdict(float)); tot = collections.defaultdict(float); usd = collections.defaultdict(float)
pos = 0.0; cost = 0.0; realized = 0.0
for s, r, ts, v, b in T:
    fi, ti = s in mem, r in mem
    if fi == ti: continue
    p = pa(ts); m = ts[:7]
    if ti:
        k = cls(s, True) + "_in"
        if k in ("dex_in", "cex_in", "lp_in"):  # acquisitions priced at the day close
            cost += v * p; pos += v
        else: cost += v * p; pos += v      # gifts/transfers in also enter at market (no known cost)
    else:
        k = cls(r, False) + "_out"
        if pos > 0:
            q = min(v, pos); avg = cost / pos
            if k in ("dex_out", "cex_out", "lp_out"): realized += q * (p - avg)
            cost -= q * avg; pos -= q
    M[m][k] += v; tot[k] += v; usd[k] += v * p
held = sum(balance_at(T, by, a) for a in mem)
P = pa(T[-1][2])
print(f"{who}: {len(mem)} wallets · holds {held/1e9:.2f}B ({100*held/SUPPLY:.2f}%) worth ${held*P:,.0f} at ${P:.2e}")
for k in sorted(tot): print(f"  {k:10s} {tot[k]/1e9:8.2f}B  ${usd[k]:>12,.0f}")
print(f"  avg-cost basis of what is held: ${cost/pos if pos else 0:.2e}/GME (${cost:,.0f}); realized on DEX/CEX/LP exits ≈ ${realized:,.0f}; unrealized ≈ ${held*P-cost:,.0f}")
print("month      " + " ".join(f"{k:>9s}" for k in ["dex_in", "dex_out", "cex_in", "cex_out", "lp_in", "lp_out", "wallet_in", "wallet_out"]))
for m in sorted(M):
    print(m, "  ", " ".join(f"{M[m][k]/1e9:9.2f}" for k in ["dex_in", "dex_out", "cex_in", "cex_out", "lp_in", "lp_out", "wallet_in", "wallet_out"]))
json.dump(dict(who=who, n=len(mem), held=held, totals=tot, usd=usd, months={m: dict(v) for m, v in M.items()}, avgCost=cost / pos if pos else None, realized=realized), open(os.path.join(D, f"entity_{who}.json"), "w"))
