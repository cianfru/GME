# Evidence-graded cluster around the focus wallet (token-flow + the focus wallet's own ETH funding).
# Link rules (only between non-infrastructure addresses; pools/routers/contracts/exchanges never link anyone):
#   deposit — both wallets sent GME to the same exchange DEPOSIT address. On MEXC/Gate a deposit address belongs
#             to ONE account, so co-depositors share an exchange account. Only addresses with ≤10 depositors.
#   seed    — B had never held GME and A's transfer was its first (≥ MIN_USD at that day's price)
#   drain   — A sent ≥90% of its balance to B in one transfer (≥ MIN_USD)
#   ethfund — the focus wallet funded B with ≥0.1 ETH and B traded GME afterwards
# Tier 1 = linked straight to the focus wallet; Tier 2 = linked to a Tier-1 wallet. Wallets that only SENT ETH
# to the focus wallet are listed as ETH sources, never merged (an ETH payment can be an OTC buyer).
# The deployer's one transfer to the focus wallet is reported, not merged. Over-merging overstates coordination.
import sys, json, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
MIN_USD = float(os.environ.get("MIN_USD", 2000)); MAX_DEP = 10; HUB = 40
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
out_to = collections.defaultdict(lambda: collections.defaultdict(float)); in_from = collections.defaultdict(lambda: collections.defaultdict(float))
first_dep = {}
for s, r, ts, v, b in T:
    out_to[s][r] += v; in_from[r][s] += v; first_dep.setdefault((s, r), ts)
deposit = {}
for a, o in out_to.items():
    if a in infra: continue
    tot = sum(o.values()); cx = sum(v for k, v in o.items() if k in CEX)
    deps = [k for k in in_from[a] if k not in infra]
    if tot > 0 and cx / tot >= 0.95 and 2 <= len(deps) <= MAX_DEP:
        deposit[a] = EX[max((k for k in o if k in CEX), key=lambda k: o[k])]["name"]
E = collections.defaultdict(list)
def add(a, b, kind, d, amt, usd, extra=None):
    E[a].append(dict(o=b, kind=kind, d=d, amt=amt, usd=usd, x=extra)); E[b].append(dict(o=a, kind=kind, d=d, amt=amt, usd=usd, x=extra))
bal = collections.defaultdict(float); seen = set()
for s, r, ts, v, b in T:
    if s not in infra and r not in infra and s != r and r not in deposit and s not in deposit:
        usd = v * pa(ts)
        if usd >= MIN_USD:
            if r not in seen: add(s, r, "seed", ts[:10], v, usd)
            elif bal[s] > 0 and v >= 0.9 * bal[s]: add(s, r, "drain", ts[:10], v, usd)
    bal[s] -= v; bal[r] += v; seen.add(r)
for d, venue in deposit.items():
    deps = [k for k in in_from[d] if k not in infra and in_from[d][k] * pa(first_dep[(k, d)]) >= MIN_USD]
    for i in range(len(deps)):
        for j in range(i + 1, len(deps)):
            add(deps[i], deps[j], "deposit", min(first_dep[(deps[i], d)], first_dep[(deps[j], d)])[:10], None, None, d)
tx = json.load(open(os.path.join(D, "focus_eth.json")))   # compact ETH history of the focus wallet (refresh_focus.py)
eth_sources = collections.defaultdict(lambda: [0.0, 0, None, None])
for t in tx:
    fr, to, eth, ts = t["from"], t["to"], t["eth"], t["ts"]
    if eth <= 0: continue
    if fr == FOCUS and to in by and to not in infra and to not in deposit and eth >= 0.1: add(FOCUS, to, "ethfund", ts[:10], eth, None)
    if to == FOCUS and fr != FOCUS and not t.get("fromContract"):
        e = eth_sources[fr]; e[0] += eth; e[1] += 1; e[2] = min(e[2] or "9", ts[:10]); e[3] = max(e[3] or "", ts[:10])
deg = {a: len({e["o"] for e in es if e["kind"] == "seed"}) for a, es in E.items()}
tier = {FOCUS: 0}; why = {FOCUS: []}
for t in (1, 2):
    for a in [x for x, k in tier.items() if k == t - 1]:
        if a != FOCUS and deg.get(a, 0) > HUB: continue          # a distributor: don't expand through it
        for e in E[a]:
            b = e["o"]
            if b in (DEPLOYER,): continue
            if b not in tier: tier[b] = t; why[b] = []
            if tier[b] == t: why[b].append(dict(e, frm=a))
members = []
for a, t in tier.items():
    ins, outs = flows(T, by, a)
    dex_in = sum(e[0] for k, e in ins.items() if k in infra and k not in CEX); dex_out = sum(e[0] for k, e in outs.items() if k in infra and k not in CEX)
    members.append(dict(a=a, tier=t, bal=balance_at(T, by, a), dexIn=dex_in, dexOut=dex_out,
                        cexIn=sum(e[0] for k, e in ins.items() if k in CEX), cexOut=sum(e[0] for k, e in outs.items() if k in CEX or k in deposit),
                        first=min([e[2] for e in ins.values()] or ["-"]), last=max([e[3] for e in list(ins.values()) + list(outs.values())] or ["-"]),
                        kinds=sorted({w["kind"] for w in why[a]}), evidence=why[a][:6]))
members.sort(key=lambda m: (m["tier"], -m["bal"]))
src = sorted(([a] + v for a, v in eth_sources.items()), key=lambda x: -x[1])
dep_used = sorted({w["x"] for m in members for w in m["evidence"] if w["kind"] == "deposit"})
json.dump(dict(minUsd=MIN_USD, deposits={d: deposit[d] for d in dep_used}, members=members, ethSources=src[:40],
               deployerLink=dict(date="2024-11-01", tokens=0.937e9, note="deployer sent its last 0.937B to the focus wallet; the focus wallet burned 0.937B the next day")),
          open(os.path.join(D, "focus_cluster.json"), "w"), default=str)
for t in (0, 1, 2):
    ms = [m for m in members if m["tier"] == t]
    print(f"tier {t}: {len(ms)} wallets · hold {sum(m['bal'] for m in ms)/1e9:.2f}B ({100*sum(m['bal'] for m in ms)/SUPPLY:.2f}%) · links {collections.Counter(k for m in ms for k in m['kinds'])}")
print("all:", len(members), "wallets hold %.2fB = %.2f%% of supply" % (sum(m["bal"] for m in members) / 1e9, 100 * sum(m["bal"] for m in members) / SUPPLY))
print("deposit addresses used:", {d: deposit[d] for d in dep_used})
for m in members:
    if m["bal"] > 1e8 or m["tier"] <= 1:
        ev = "; ".join(f"{w['kind']} {w['frm'][:8]}↔ {w['d']}" + (f" {w['amt']/1e9:.2f}B" if w['kind'] in ('seed','drain') else (f" {w['amt']:.1f}ETH" if w['kind']=='ethfund' else f" via {w['x'][:8]}")) for w in m["evidence"][:3])
        print(f"T{m['tier']} {m['a']} bal {m['bal']/1e9:6.2f}B dexIn {m['dexIn']/1e9:5.1f} dexOut {m['dexOut']/1e9:5.1f} cexOut {m['cexOut']/1e9:4.1f} first {m['first']} last {m['last']} | {ev}")
print("\nETH sources into the focus wallet (not merged):")
for a, eth, n, d0, d1 in src[:15]: print("  ", a, f"{eth:.1f} ETH", n, "tx", d0, "→", d1, "GME-active" if a in by else "")
