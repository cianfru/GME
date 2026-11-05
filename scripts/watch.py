# Daily watch: compares today's state with the previous run and writes alerts.
#   data/alerts/latest.json  — today's alerts + summary      data/alerts/log.jsonl — one line per run
#   data/watch_state.json    — the state the next run compares against
# Watched: the focus wallet's cluster, the Coinbase group, every owner on the quiet-accumulator list (stealth.json),
# every buy-and-forward holding wallet (vaults90.json) and the wallets created in the 24–25 Sep 2025 reshuffle.
import sys, json, collections, os, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {"0x05391bd57d8c6fb30d9c39f6618f2207893922dc", "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
outs = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: outs[s][r] += v
deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(x for k, x in o.items() if k in CEX) / sum(o.values()) >= 0.95}
from groups import base_groups, with_attached, short
groups, FOC, CBG, ST, V = base_groups()
groups = with_attached(groups)     # + wallets the entity registry attached by following the coins (moves into them are internal)
NOW = T[-1][2]
SP = os.path.join(D, "watch_state.json")
prev = json.load(open(SP)) if os.path.exists(SP) else None
since = prev["asOf"] if prev else (datetime.datetime.fromisoformat(NOW[:19]) - datetime.timedelta(days=1)).isoformat() + "Z"
bal = collections.defaultdict(float); pool = 0.0
for s, r, ts, v, b in T:
    bal[s] -= v; bal[r] += v
pool = bal[PAIR]
price = pa(NOW)
member = {}
for g, ws in groups.items():
    for a in ws: member.setdefault(a, g)
alerts = []
def add(kind, sev, text, **kw): alerts.append(dict(kind=kind, severity=sev, text=text, **kw))
# 1) transfers out of watched wallets since the last run
flow = collections.defaultdict(lambda: collections.Counter())
for s, r, ts, v, b in T:
    if ts <= since: continue
    gs, gr = member.get(s), member.get(r)
    if gs and gs != gr:
        if r in CEX or r in deplike: flow[gs]["to exchange"] += v
        elif r in infra and r not in LP: flow[gs]["sold on DEX"] += v
        elif r in LP: flow[gs]["to liquidity"] += v
        elif r == DEAD: flow[gs]["burned"] += v
        else: flow[gs]["to other wallets"] += v
    if gr and gs != gr:
        if s in infra and s not in CEX and s not in LP: flow[gr]["bought on DEX"] += v
        elif s in CEX: flow[gr]["from exchange"] += v
        else: flow[gr]["from other wallets"] += v
for g, c in flow.items():
    for k, v in c.items():
        if v < 5e7: continue                                   # ignore < 50M GME (~$300)
        pct = 100 * v / SUPPLY
        sev = "high" if k in ("to exchange", "sold on DEX") and pct >= 0.05 else ("medium" if k in ("to exchange", "sold on DEX", "to other wallets") else "info")
        add("flow", sev, f"{g}: {k} {v/1e9:.2f}B GME (~${v*price:,.0f}, {pct:.2f}% of supply)", group=g, what=k, tokens=v)
# 2) new holding wallets and new accumulators
if prev:
    for v, x in V.items():
        if v not in prev.get("vaults", []):
            add("new_vault", "high", f"New buy-and-forward holding wallet {short(v)}: {len(x['feeders'])} fresh wallet(s) forwarded {x['tok']/1e9:.2f}B (bought for ${x['usd']:,.0f})", wallet=v)
    pst = set(prev.get("stealth", []))
    for r in ST:
        if r["owner"] not in pst and not (set(r["wallets"]) & FOC):
            add("new_accumulator", "medium", f"New quiet accumulator {short(r['wallets'][0])} ({r['n']} wallet(s)): +{r['net']/1e9:.2f}B in 90 days ({r['pct']:.2f}% of supply), spent ${r['usd']:,.0f}; {'; '.join(r['tags'])}", wallet=r["wallets"][0])
# 3) pool reserve
if prev:
    d = pool - prev["pool"]
    what = "no change" if abs(d) < 1e6 else ("net selling into the pool" if d > 0 else "net buying out of the pool")
    add("pool", "info", f"Pool GME {'+' if d >= 0 else ''}{d/1e9:.2f}B since last run ({what}); pool now {pool/1e9:.2f}B, price ${price:.3e}", delta=d)
gbal = {g: sum(max(bal[a], 0) for a in ws) for g, ws in groups.items()}
if prev:
    for g, b in gbal.items():
        pb = prev["groups"].get(g)
        if pb is not None and abs(b - pb) >= 0.0005 * SUPPLY:
            add("balance", "medium" if b < pb else "info", f"{g}: holdings {'+' if b >= pb else ''}{(b-pb)/1e9:.2f}B since last run, now {b/1e9:.2f}B ({100*b/SUPPLY:.2f}%)", group=g)
order = {"high": 0, "medium": 1, "info": 2}
alerts.sort(key=lambda x: order[x["severity"]])
summary = dict(asOf=NOW, since=since, price=price, mcap=price * SUPPLY, pool=pool, watchedGroups=len(groups), alerts=len(alerts),
               high=sum(1 for a in alerts if a["severity"] == "high"))
os.makedirs(os.path.join(D, "alerts"), exist_ok=True)
json.dump(dict(summary=summary, alerts=alerts), open(os.path.join(D, "alerts", "latest.json"), "w"), indent=1)
with open(os.path.join(D, "alerts", "log.jsonl"), "a") as f: f.write(json.dumps(dict(summary=summary, alerts=alerts)) + "\n")
json.dump(dict(asOf=NOW, pool=pool, groups=gbal, vaults=sorted(V), stealth=sorted(r["owner"] for r in ST),
               members={g: sorted(ws) for g, ws in groups.items()}), open(SP, "w"))
lines = [f"## GME watch · {NOW[:16]} UTC", f"Price ${price:.3e} · market cap ${price*SUPPLY/1e6:.2f}M · pool {pool/1e9:.2f}B GME · {len(groups)} watched groups", ""]
lines += [f"- **{a['severity'].upper()}** {a['text']}" for a in alerts] or ["- No alerts since the last run." if prev else "- First run: baseline saved, alerts start tomorrow."]
md = "\n".join(lines)
print(md)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(md + "\n")
