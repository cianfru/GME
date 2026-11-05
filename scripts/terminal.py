# Data for the terminal site. Daily step, AFTER watch.py (it reads the watched groups' members from watch_state.json).
#   data/terminal.json — daily series since launch (price, engine metrics, DEX flows, new wallets, pool, focus wallet
#                        and cluster holdings, cluster → exchange), the insider-watch status, 180-day holdings of every
#                        watched group, the cluster graph + member table, top holders.
#   data/wallets.json  — per-wallet history (daily balance + transfer events) for every watched wallet and top holder,
#                        loaded by the site only when a wallet is opened.
import sys, json, os, csv, collections, datetime, importlib.util, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
spec = importlib.util.spec_from_file_location("p", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pull-transfers-rpc.py"))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

T = load(); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {V3POOL, "0xc36442b4a4522e871399cd717abdd847ab11fe88"}          # liquidity adds/removes, not trades
FC = json.load(open(os.path.join(D, "focus_cluster.json")))
FOC = {m["a"] for m in FC["members"]}
REG = json.load(open(os.path.join(D, "entities.json"))) if os.path.exists(os.path.join(D, "entities.json")) else None
REG_FOCUS = next((e for e in REG["entities"] if e["kind"] == "focus"), None) if REG else None
if REG_FOCUS: FOC |= {x["a"] for x in REG_FOCUS["attached"]}      # wallets joined by following the coins count as the cluster's own
WS = json.load(open(os.path.join(D, "watch_state.json")))
# On a shared page "your wallet" reads as the viewer's; the watch files keep their original label.
relabel = lambda g: g.replace("Your wallet's cluster", "Focus wallet's cluster")
MEMBERS = {relabel(g): set(ws) for g, ws in WS.get("members", {}).items()}
NOW = T[-1][2]; TODAY = NOW[:10]

outs = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: outs[s][r] += v
deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(x for k, x in o.items() if k in CEX) / sum(o.values()) >= 0.95}
is_dex = lambda a: a in infra and a not in CEX and a not in LP and a not in (NULL, DEAD, TOKEN)   # a send to the token contract itself is not a sale
is_cex = lambda a: a in CEX or a in deplike

def kind(frm, to, me):
    """What a transfer is, seen from wallet `me`."""
    other = to if frm == me else frm
    out = frm == me
    if is_dex(other): return ("dex-sell" if out else "dex-buy"), other
    if is_cex(other): return ("cex-out" if out else "cex-in"), other
    if other == TOKEN: return ("out" if out else "in"), other
    if other in LP: return ("lp-add" if out else "lp-remove"), other
    if other == DEAD: return "burn", other
    return ("out" if out else "in"), other

# ---- daily series ---------------------------------------------------------------------------------------------
day0 = datetime.date.fromisoformat(T[0][2][:10]); day1 = datetime.date.fromisoformat(TODAY)
days = [(day0 + datetime.timedelta(days=i)).isoformat() for i in range((day1 - day0).days + 1)]
ix = {d: i for i, d in enumerate(days)}
N = len(days)
z = lambda: [0.0] * N
buy_usd, sell_usd, buy_tok, sell_tok = z(), z(), z(), z()
buyers, sellers = [set() for _ in range(N)], [set() for _ in range(N)]
new_w = z(); d_focus, d_cl, d_pool = z(), z(), z()
tx_n, tx_vol, tx_usd = z(), z(), z(); active = [set() for _ in range(N)]   # every transfer, mint included
cl_cex_tok, cl_cex_usd, cl_dexbuy, cl_dexsell, cl_cexin = z(), z(), z(), z(), z()
focus_dexsell = z()
gname = {}
for g, ws in MEMBERS.items():
    for a in ws: gname.setdefault(a, g)
d_grp = collections.defaultdict(z)
seen = set()
for s, r, ts, v, b in T:
    i = ix[ts[:10]]; px = pa(ts)
    tx_n[i] += 1; tx_vol[i] += v; tx_usd[i] += v * px
    if s not in infra: active[i].add(s)
    if r not in infra: active[i].add(r)
    if r not in infra and r not in seen: seen.add(r); new_w[i] += 1
    if is_dex(s) and r not in infra: buy_usd[i] += v * px; buy_tok[i] += v; buyers[i].add(r)
    if is_dex(r) and s not in infra: sell_usd[i] += v * px; sell_tok[i] += v; sellers[i].add(s)
    if s == FOCUS: d_focus[i] -= v
    if r == FOCUS: d_focus[i] += v
    if s == FOCUS and is_dex(r): focus_dexsell[i] += v
    if s == PAIR: d_pool[i] -= v
    if r == PAIR: d_pool[i] += v
    sf, rf = s in FOC, r in FOC
    if sf and not rf:
        d_cl[i] -= v
        if is_cex(r): cl_cex_tok[i] += v; cl_cex_usd[i] += v * px
        if is_dex(r): cl_dexsell[i] += v
    if rf and not sf:
        d_cl[i] += v
        if is_dex(s): cl_dexbuy[i] += v
        if is_cex(s): cl_cexin[i] += v
    gs, gr = gname.get(s), gname.get(r)
    if gs and gs != gr: d_grp[gs][i] -= v
    if gr and gs != gr: d_grp[gr][i] += v

def cum(a):
    out, t = [], 0.0
    for x in a: t += x; out.append(t)
    return out
focus_bal, cl_bal, pool_bal = cum(d_focus), cum(d_cl), cum(d_pool)

pmap = {r[0]: float(r[1]) for r in csv.reader(open(os.path.join(D, "prices.csv"))) if r[0] != "day"}
eng = {r["d"]: r for r in json.load(open(os.path.join(D, "engine", "onchain.json")))} if os.path.exists(os.path.join(D, "engine", "onchain.json")) else {}
E = lambda k, f=lambda x: x: [(f(eng[d][k]) if d in eng and eng[d].get(k) is not None else None) for d in days]
r2 = lambda xs, n=2: [None if x is None else round(x, n) for x in xs]
B = lambda xs: [round(x / 1e9, 4) for x in xs]

daily = dict(
    d=days, price=[pmap.get(d) for d in days],
    rp=E("rp"), mvrv=E("mvrv"), sip=E("sip"), sopr=E("sopr"), holders=E("holders"), top10=E("top10"), top100=E("top100"),
    whalePct=E("whalePct"), whaleN=E("whaleN"), nrpl=E("nrpl"), liveliness=E("liveliness"),
    age=[eng[d]["age"] if d in eng else None for d in days], wealth=[eng[d]["wealth"] if d in eng else None for d in days],
    cexBal=E("cexBal", lambda x: round(x / 1e9, 4)),
    buyUsd=r2(buy_usd, 0), sellUsd=r2(sell_usd, 0), buyers=[len(x) for x in buyers], sellers=[len(x) for x in sellers],
    newWallets=[int(x) for x in new_w], pool=B(pool_bal), focus=B(focus_bal), cluster=B(cl_bal),
    clusterToCex=B(cl_cex_tok), clusterToCexUsd=r2(cl_cex_usd, 0), clusterDexBuy=B(cl_dexbuy), clusterDexSell=B(cl_dexsell),
    clusterFromCex=B(cl_cexin), focusDexSell=B(focus_dexsell),
    tx=[int(x) for x in tx_n], txVol=B(tx_vol), txUsd=r2(tx_usd, 0), active=[len(x) for x in active],
)

# ---- insider watch: what the focus wallet's cluster did lately -------------------------------------------------
def win(a, n): return sum(a[-n:])
w = {n: dict(net=win(d_cl, n), toCex=win(cl_cex_tok, n), toCexUsd=win(cl_cex_usd, n), dexBuy=win(cl_dexbuy, n),
             dexSell=win(cl_dexsell, n), fromCex=win(cl_cexin, n), focusDexSell=win(focus_dexsell, n)) for n in (1, 7, 30, 90)}
thr = 0.0005 * SUPPLY                                          # 0.05% of supply
if w[30]["toCex"] >= thr: status, why = "DISTRIBUTING", "sent GME to exchanges in the last 30 days"
elif w[30]["dexSell"] > w[30]["dexBuy"] and w[30]["net"] < 0: status, why = "SELLING", "sold more than it bought on the DEX in 30 days"
elif w[30]["net"] > thr: status, why = "ACCUMULATING", "holdings grew in the last 30 days"
else: status, why = "HOLDING", "no meaningful change in 30 days"
tripwire = []
if w[7]["toCex"] > 0: tripwire.append(f"{w[7]['toCex']/1e9:.2f}B GME sent to exchanges in the last 7 days")
if w[30]["focusDexSell"] > 0: tripwire.append(f"the focus wallet sold {w[30]['focusDexSell']/1e9:.2f}B on the DEX in the last 30 days")
insider = dict(status=status, why=why, armed=bool(tripwire), tripwire=tripwire,
               focusDexSellEver=sum(focus_dexsell), windows={str(k): v for k, v in w.items()})

# ---- watched groups: last 180 days of holdings ------------------------------------------------------------------
cur = {relabel(g): b for g, b in WS["groups"].items()}
K = 180
groups = []
for g in MEMBERS:
    d = d_grp[g]; c = cur.get(g, 0.0); series = [0.0] * K
    for k in range(K - 1, -1, -1):              # walk back from today's balance
        series[k] = c; c -= d[N - K + k]
    b0 = cur.get(g, 0.0)
    groups.append(dict(name=g, n=len(MEMBERS[g]), bal=b0, series=[round(x / 1e9, 3) for x in series],
                       d1=b0 - series[-2], d7=b0 - series[-8], d30=b0 - series[-31],
                       members=sorted(MEMBERS[g])[:200]))
groups.sort(key=lambda x: -x["bal"])

# ---- current balances, top holders --------------------------------------------------------------------------------
bal = collections.Counter(); first = {}; last = {}
for s, r, ts, v, b in T:
    bal[s] -= v; bal[r] += v; first.setdefault(r, ts); last[s] = ts; last[r] = ts
top = [dict(a=a, bal=b, pct=100 * b / SUPPLY, group=gname.get(a), first=first.get(a, "")[:10], last=last.get(a, "")[:10])
       for a, b in bal.most_common(400) if a not in infra and b > 0][:50]

# ---- the cluster: graph + members ----------------------------------------------------------------------------------
kind_of = {"seed": "gme", "drain": "gme", "deposit": "deposit", "ethfund": "eth"}
links = {}
for m in FC["members"]:
    for e in m.get("evidence", []):
        a, b2 = e["o"], e.get("frm")
        if b2 in FOC and a in FOC and a != b2:
            links[tuple(sorted((a, b2))) + (kind_of.get(e["kind"], e["kind"]),)] = 1
members = [dict(a=m["a"], bal=bal[m["a"]], tier=m["tier"], kinds=sorted(set(kind_of.get(k, k) for k in m["kinds"])),
                first=first.get(m["a"], "")[:10], last=last.get(m["a"], "")[:10]) for m in FC["members"]]
if REG_FOCUS:   # wallets joined by following the coins: a node linked by the GME transfer that tied it in
    tier_of = {m["a"]: m["tier"] for m in members}
    for x in REG_FOCUS["attached"]:
        if x["a"] in tier_of: continue
        tier_of[x["a"]] = tier_of.get(x["frm"], 2) + 1
        members.append(dict(a=x["a"], bal=bal[x["a"]], tier=tier_of[x["a"]], kinds=["gme"], first=first.get(x["a"], "")[:10], last=last.get(x["a"], "")[:10], auto=x["d"]))
        links[tuple(sorted((x["a"], x["frm"]))) + ("gme",)] = 1
cluster = dict(nodes=members, links=[dict(s=k[0], t=k[1], kind=k[2]) for k in links],
               deposits=FC.get("deposits", {}))

# ---- live pool reserves ----------------------------------------------------------------------------------------------
eth = [(r[0], float(r[1])) for r in csv.reader(open(os.path.join(D, "eth_prices.csv"))) if r[0] != "day"]
pool_gme, pool_weth = pool_bal[-1], None
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": PAIR, "data": "0x0902f1ac"}, "latest"]}).encode()
for url in p.RPCS:
    try:
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "curl/8.5.0"})
        with p._OPENER.open(req, timeout=30) as rr: h = json.load(rr)["result"][2:]
        pool_weth = int(h[0:64], 16) / 1e18; pool_gme = int(h[64:128], 16) / 1e9; break
    except Exception as e:
        print("getReserves via", url, "failed:", e)
if pool_weth is None: pool_weth = (daily["price"][-1] or daily["price"][-2]) * pool_gme / eth[-1][1]

urpd = json.load(open(os.path.join(D, "engine", "urpd.json"))) if os.path.exists(os.path.join(D, "engine", "urpd.json")) else None
cohorts = json.load(open(os.path.join(D, "cohorts.json")))["cohorts"] if os.path.exists(os.path.join(D, "cohorts.json")) else {}
runs = json.load(open(os.path.join(D, "runs.json"))) if os.path.exists(os.path.join(D, "runs.json")) else []
# ---- the monitor: every wallet with ≥0.1% of supply now or at any point in the last 90 days, plus every watched /
#      owner-group wallet, and all their transfers in those 90 days (hourly, by counterparty) ---------------------------
H90 = 90 * 24
t0 = datetime.datetime.fromisoformat(NOW[:19]) - datetime.timedelta(hours=H90)
t0s = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
thr_mon = 0.001 * SUPPLY
recent = [x for x in T if x[2] > t0s]
start = collections.Counter(bal)
for s, r, ts, v, b in recent: start[s] += v; start[r] -= v
run, peak = collections.Counter(start), set()
for s, r, ts, v, b in recent:
    run[s] -= v; run[r] += v
    if run[r] >= thr_mon: peak.add(r)
MON = {a for a in set(bal) | peak if a not in infra and (bal[a] >= thr_mon or start[a] >= thr_mon or a in peak)}

# Owner groups, most specific first: the focus cluster, the watched groups, then the linked-wallet groups found by
# cluster_all.py that hold a monitored wallet. Groups flagged as over-merged (>60 wallets) are never used.
owners, owner_of = [], {}
def add_owner(name, ws, kind, eid=None):
    ws = [a for a in sorted(ws) if a not in infra and a not in owner_of]
    if len(ws) < 1: return
    k = len(owners); owners.append(dict(name=name, kind=kind, n=len(ws), id=eid))
    for a in ws: owner_of[a] = k
PROV = {}
if REG:   # owners = the entity registry (same members, ids and order as the entity cards)
    for e in REG["entities"]: add_owner(e["name"], e["members"], e["kind"], e["id"])
    for e in REG["entities"]:
        k = next((i for i, o in enumerate(owners) if o["id"] == e["id"]), -1)
        for x in e["provisional"]:
            if x["a"] not in owner_of and x["a"] not in infra: PROV[x["a"]] = k
add_owner("Focus wallet's cluster", FOC, "focus")
for g, ws in sorted(MEMBERS.items(), key=lambda kv: -cur.get(kv[0], 0)):
    if g != "Focus wallet's cluster": add_owner(g, ws, "coinbase" if g.startswith("Coinbase") else "watched")
ENT = json.load(open(os.path.join(D, "entities_all.json")))["entities"] if os.path.exists(os.path.join(D, "entities_all.json")) else []
for e in ENT:
    ws = set(e["wallets"])
    if e.get("flagged") or not (ws & MON): continue
    lead = max(ws, key=lambda a: bal[a])
    add_owner(f"Linked group {lead[:6]}…{lead[-4:]}", ws, "linked")
TRACK = MON | set(owner_of) | set(PROV)
TRACK -= infra
def cat(a):
    if is_cex(a): return "C"
    if a in LP: return "L"
    if a in (DEAD, NULL): return "B"
    if a == TOKEN: return "T"
    if is_dex(a): return "D"
    return None
A, ai = [], {}
def idx(a):
    if a not in ai: ai[a] = len(A); A.append(a)
    return ai[a]
for a in sorted(TRACK, key=lambda a: -bal[a]): idx(a)
edges = collections.Counter()
for s, r, ts, v, b in recent:
    if s == r or not (s in TRACK or r in TRACK): continue
    h = int((datetime.datetime.fromisoformat(ts[:19]) - t0).total_seconds() // 3600)
    src = idx(s) if s in TRACK else (cat(s) or idx(s))
    dst = idx(r) if r in TRACK else (cat(r) or idx(r))
    edges[(h, src, dst)] += v
mon = dict(
    start=t0s, hours=H90, A=A,
    M=[[round(bal[a] / 1e9, 4), owner_of.get(a, -1), int(a in MON), first.get(a, "")[:10], last.get(a, "")[:10], PROV.get(a, -1)] if a in TRACK else None for a in A],
    owners=owners,
    e=[[h, s_, d_, round(v / 1e9, 5)] for (h, s_, d_), v in sorted(edges.items(), key=lambda kv: (kv[0][0], str(kv[0][1]), str(kv[0][2])))],
)

# ---- index facts and the largest movements -----------------------------------------------------------------------
def window_active(hours):
    since = (datetime.datetime.fromisoformat(NOW[:19]) - datetime.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    a, n = set(), 0
    for s_, r_, ts, v, b in reversed(T):
        if ts <= since: break
        n += 1
        if s_ not in infra: a.add(s_)
        if r_ not in infra: a.add(r_)
    return n, len(a)
label = lambda a: ("DEX" if is_dex(a) else "Exchange" if is_cex(a) else "Liquidity" if a in LP else "Burn" if a == DEAD
                   else "Mint" if a == NULL else "Token contract" if a == TOKEN else None)
big = sorted((x for x in recent if x[0] != x[1] and not (x[0] in infra and x[1] in infra)), key=lambda x: -x[3])[:60]   # skip plumbing between two infra addresses
index = dict(
    indexedAt=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    lastTransfer=NOW, transfers=len(T), firstTransfer=T[0][2],
    held=sum(v for a, v in bal.items() if a not in infra and v > 0), burned=bal[DEAD],
    **{f"tx{h}h": window_active(h)[0] for h in (24, 168, 720)}, **{f"active{h}h": window_active(h)[1] for h in (24, 168, 720)},
)
moves = [dict(t=ts, f=s_, to=r_, fl=label(s_), tl=label(r_), fg=gname.get(s_), tg=gname.get(r_), tok=round(v / 1e9, 4),
              usd=round(v * pa(ts))) for s_, r_, ts, v, b in big]

out = dict(
    asOf=NOW, index=index, moves=moves, daily=daily, insider=insider, groups=groups, top=top, cluster=cluster, mon=mon,
    pool=dict(gme=pool_gme, weth=pool_weth, ethUsd=eth[-1][1]),
    urpd=dict(spot=urpd["spot"], buckets=[dict(lo=x["lo"], hi=x["hi"], pct=x["pct"]) for x in urpd["buckets"]]) if urpd else None,
    cohorts=[dict(name=k.split(" ", 1)[1], wallets=v["wallets"], holdNow=v["holdNow"], buyUsd=v["buyUsd"], sellUsd=v["sellUsd"]) for k, v in sorted(cohorts.items())],
    runs=[dict(name=r["name"], a=r["a"], b=r["b"], mult=r["mult"]) for r in runs if r["name"].startswith("Run")],
)
json.dump(out, open(os.path.join(D, "terminal.json"), "w"), separators=(",", ":"))

# ---- per-wallet history for the drill-down ---------------------------------------------------------------------------
watch = set().union(*MEMBERS.values()) if MEMBERS else set()
watch |= {t["a"] for t in top} | FOC | TRACK
watch -= infra
ev = collections.defaultdict(list)
for s, r, ts, v, b in T:
    if s == r: continue
    for me in (s, r):
        if me in watch:
            k, other = kind(s, r, me)
            ev[me].append((ts, -v if me == s else v, k, other))
wallets = {}
for a in watch:
    e = ev.get(a, [])
    series, run, cur_d = [], 0.0, None
    for ts, dv, k, o in e:
        run += dv
        if series and series[-1][0] == ts[:10]: series[-1][1] = round(run / 1e9, 4)
        else: series.append([ts[:10], round(run / 1e9, 4)])
    # Merge transfers of the same kind with the same counterparty on the same day (one line per action).
    agg = collections.OrderedDict()
    for ts, dv, k, o in e:
        key = (ts[:10], k, o)
        if key in agg: agg[key][1] += dv; agg[key][3] += abs(dv) * pa(ts)
        else: agg[key] = [ts[:10], dv, k, abs(dv) * pa(ts), o]
    evs = [[x[0], round(x[1] / 1e9, 4), x[2], round(x[3]), x[4]] for x in agg.values()]
    wallets[a] = dict(bal=round(bal[a] / 1e9, 4), group=gname.get(a) or ("Focus wallet's cluster" if a in FOC else None),
                      first=first.get(a, "")[:10], last=last.get(a, "")[:10], n=len(evs), series=series, events=evs[-400:])
json.dump(wallets, open(os.path.join(D, "wallets.json"), "w"), separators=(",", ":"))

print(f"terminal.json: {N} days · insider {status} ({why}){' · TRIPWIRE ' + '; '.join(tripwire) if tripwire else ''} · "
      f"{len(groups)} groups · monitor {len(MON)} wallets ≥0.1% ({len(TRACK)} tracked, {len(owners)} owners, {len(edges)} flow edges) · pool {pool_gme/1e9:.2f}B / {pool_weth:.1f} WETH · focus wallet DEX sells ever {sum(focus_dexsell)/1e9:.2f}B")
print(f"wallets.json: {len(wallets)} wallets, {sum(w_['n'] for w_ in wallets.values())} events")
