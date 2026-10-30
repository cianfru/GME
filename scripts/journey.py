# Data for the site's visual journey → data/journey.json. Daily step, after cluster.py / cohorts.py.
#   price + ATH · daily balance of the focus wallet and its cluster · the cluster's monthly sends to exchanges ·
#   live pool reserves (getReserves) · the cluster as a graph · cost basis of held supply (engine URPD).
import sys, json, os, csv, collections, datetime, importlib.util, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
spec = importlib.util.spec_from_file_location("p", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pull-transfers-rpc.py"))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

T = load(); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
FC = json.load(open(os.path.join(D, "focus_cluster.json")))
FOC = {m["a"] for m in FC["members"]}
NOW = T[-1][2]

# Deposit-like addresses: not labelled, but forward ≥95% of what they send to a known exchange.
outs = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: outs[s][r] += v
deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(x for k, x in o.items() if k in CEX) / sum(o.values()) >= 0.95}

# Daily balances of the focus wallet and of the whole cluster (today's members), in GME.
day0 = datetime.date.fromisoformat(T[0][2][:10]); day1 = datetime.date.fromisoformat(NOW[:10])
delta_f = collections.Counter(); delta_c = collections.Counter(); to_cex = collections.Counter()
for s, r, ts, v, b in T:
    d = ts[:10]
    if s == FOCUS: delta_f[d] -= v
    if r == FOCUS: delta_f[d] += v
    if s in FOC and r not in FOC:
        delta_c[d] -= v
        if r in CEX or r in deplike: to_cex[d[:7]] += v * pa(ts)
    if r in FOC and s not in FOC: delta_c[d] += v
days, focus, cluster = [], [], []
bf = bc = 0.0; d = day0
while d <= day1:
    k = d.isoformat(); bf += delta_f[k]; bc += delta_c[k]
    days.append(k); focus.append(round(bf / 1e9, 3)); cluster.append(round(bc / 1e9, 3)); d += datetime.timedelta(days=1)

px = [(r[0], float(r[1])) for r in csv.reader(open(os.path.join(D, "prices.csv"))) if r[0] != "day"]
ath = max(px, key=lambda x: x[1])
eth = [(r[0], float(r[1])) for r in csv.reader(open(os.path.join(D, "eth_prices.csv"))) if r[0] != "day"]
eth_usd = eth[-1][1]

# Pool reserves straight from the pair (token0 = WETH, token1 = GME). Fallback: GME balance + implied WETH.
pool_gme = sum(v for s, r, ts, v, b in T if r == PAIR) - sum(v for s, r, ts, v, b in T if s == PAIR)
pool_weth = None
try:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": PAIR, "data": "0x0902f1ac"}, "latest"]}).encode()
    for url in p.RPCS:
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "curl/8.5.0"})
            with p._OPENER.open(req, timeout=30) as rr: h = json.load(rr)["result"][2:]
            pool_weth = int(h[0:64], 16) / 1e18; pool_gme = int(h[64:128], 16) / 1e9; break
        except Exception as e:
            print("getReserves via", url, "failed:", e)
except Exception as e:
    print("getReserves failed:", e)
if pool_weth is None: pool_weth = px[-1][1] * pool_gme / eth_usd

# The cluster as a graph: members + the link that put each one in (only links between members are drawn).
kind_of = {"seed": "gme", "drain": "gme", "deposit": "deposit", "ethfund": "eth"}
links = {}
for m in FC["members"]:
    for e in m.get("evidence", []):
        a, b2 = e["o"], e.get("frm")
        if b2 in FOC and a in FOC and a != b2:
            key = tuple(sorted((a, b2))) + (kind_of.get(e["kind"], e["kind"]),)
            links[key] = links.get(key, 0) + 1
graph = dict(
    nodes=[dict(a=m["a"], bal=round(m["bal"] / 1e9, 4), tier=m["tier"], kinds=sorted(set(kind_of.get(k, k) for k in m["kinds"])),
                cexOut=round((m.get("cexOut") or 0) / 1e9, 3), dexOut=round((m.get("dexOut") or 0) / 1e9, 3)) for m in FC["members"]],
    links=[dict(s=k[0], t=k[1], kind=k[2]) for k in links])

urpd = json.load(open(os.path.join(D, "engine", "urpd.json"))) if os.path.exists(os.path.join(D, "engine", "urpd.json")) else None
cohorts = json.load(open(os.path.join(D, "cohorts.json")))["cohorts"] if os.path.exists(os.path.join(D, "cohorts.json")) else {}
launch = json.load(open(os.path.join(D, "page_data.json"))).get("launch", []) if os.path.exists(os.path.join(D, "page_data.json")) else []
runs = json.load(open(os.path.join(D, "runs.json"))) if os.path.exists(os.path.join(D, "runs.json")) else []
b0 = json.load(open(os.path.join(D, "launch_block0.json"))) if os.path.exists(os.path.join(D, "launch_block0.json")) else []

out = dict(
    asOf=NOW, price=[[d, v] for d, v in px], ath=dict(d=ath[0], p=ath[1]),
    days=days, focus=focus, cluster=cluster,
    clusterToCex=sorted([m, round(u)] for m, u in to_cex.items()),
    pool=dict(gme=pool_gme, weth=pool_weth, ethUsd=eth_usd),
    graph=graph,
    urpd=dict(spot=urpd["spot"], buckets=[dict(lo=x["lo"], hi=x["hi"], pct=x["pct"]) for x in urpd["buckets"]]) if urpd else None,
    cohorts=[dict(name=k.split(" ", 1)[1], wallets=v["wallets"], holdNow=v["holdNow"], buyUsd=v["buyUsd"], sellUsd=v["sellUsd"]) for k, v in sorted(cohorts.items())],
    launch=dict(steps=launch, wallets=len(b0), funders=len({x.get("g") for x in b0}), eth=sum(x.get("eth", 0) for x in b0)),
    runs=[dict(name=r["name"], a=r["a"], b=r["b"], mult=r["mult"]) for r in runs],
)
json.dump(out, open(os.path.join(D, "journey.json"), "w"), separators=(",", ":"))
print(f"journey.json: {len(days)} days · focus {focus[-1]:.2f}B · cluster {cluster[-1]:.2f}B · pool {pool_gme/1e9:.2f}B GME / {pool_weth:.1f} WETH · "
      f"graph {len(graph['nodes'])} nodes {len(graph['links'])} links · cluster→exchange ${sum(to_cex.values()):,.0f}")
