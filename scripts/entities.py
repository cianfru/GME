# Entity registry: every group of linked wallets as one entity with a stable id, followed run to run.
#   data/entities.json — read back by the next run (stable ids, wallets attached by following the coins), by watch.py
#                        and terminal.py (so attached wallets count as the group's own) and by the site (entity cards,
#                        entity flow map, tripwire alerts).
#
# Sources, highest priority first (a wallet belongs to one entity only): the focus wallet's cluster, the Coinbase
# group, every watched group (accumulators, holding wallets, Sep-2025 wallets), then the unflagged linked groups of
# entities_all.json that hold ≥0.05% of supply.
#
# Follow the coins (last 90 days, no hop limit): a wallet joins an entity when a DIRECT linking rule fires with one of
# its members — seed (the wallet's first GME came from a member, ≥$2k) or drain (one sent the other ≥90% of its
# balance in one transfer, ≥$2k). Never through infrastructure, contracts, exchange deposit addresses or a sender that
# seeded >40 wallets (a distributor). Linked groups stop growing at 60 wallets (flagged); at most 25 joins per entity
# per run. Joins are kept on later runs. A wallet that received ≥$2k from an entity in 30 days without a rule firing is
# listed as PROVISIONAL: shown, never counted.
#
# Per entity: holdings and 90-day series (today's members, so moves between its own wallets cancel), flows by channel
# over 1/7/30/90 days, a status per window, a cost basis (FIFO over the entity's external flows; coins that arrived by
# transfer are costed at that day's price), evidence strength (focus cluster), "forming" flags and tripwires since the
# last run.
import sys, json, os, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
from groups import base_groups, short

MIN_USD, HUB, CAP, PER_RUN = 2000.0, 40, 60, 25
WIN = (24, 168, 720, 2160)
LINKED_MIN = 0.0005 * SUPPLY
CH = ["dexIn", "dexOut", "cexIn", "cexOut", "wIn", "wOut", "entIn", "entOut", "othIn", "othOut", "internal", "n"]
relabel = lambda g: g.replace("Your wallet's cluster", "Focus wallet's cluster")
iso = lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")
parse = lambda ts: datetime.datetime.fromisoformat(ts[:19])

T = load(); pa = prices()
PX = exact_prices(T, pa)       # cost basis uses exact execution prices for DEX trades (trades.py); rules keep the day's close
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {V3POOL, "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
AT = json.load(open(os.path.join(D, "addr-types.json"))) if os.path.exists(os.path.join(D, "addr-types.json")) else {}
NOW = T[-1][2]; now_dt = parse(NOW); TODAY = NOW[:10]; spot = pa(NOW)
cut = lambda h: iso(now_dt - datetime.timedelta(hours=h))
RP = os.path.join(D, "entities.json")
prev = json.load(open(RP)) if os.path.exists(RP) else None
WSP = os.path.join(D, "watch_state.json")
since = prev["asOf"] if prev else (json.load(open(WSP))["asOf"] if os.path.exists(WSP) else cut(24))

# ---- one pass over the full history: balances, first receipts, drains, seeds per sender, exchange-deposit-likes ----
bal = collections.Counter(); first_in = {}; first_seen = {}; last_seen = {}; drains = []; seeds = collections.Counter()
outs = collections.defaultdict(lambda: collections.defaultdict(float)); seen = set()
for s, r, ts, v, b in T:
    outs[s][r] += v
    if s not in infra and r not in infra and s != r:
        usd = v * pa(ts)
        if r not in seen:
            first_in[r] = (s, ts, v, usd)
            if usd >= MIN_USD: seeds[s] += 1
        elif usd >= MIN_USD and bal[s] > 0 and v >= 0.9 * bal[s]:
            drains.append((s, r, ts, v, usd))
    bal[s] -= v; bal[r] += v; seen.add(r); first_seen.setdefault(r, ts); last_seen[s] = ts; last_seen[r] = ts
deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(x for k, x in o.items() if k in CEX) / sum(o.values()) >= 0.95}
is_dex = lambda a: a in infra and a not in CEX and a not in LP and a not in (NULL, DEAD, TOKEN)
is_cex = lambda a: a in CEX or a in deplike
ok = lambda a: a not in infra and a not in deplike and AT.get(a) != "contract"

# ---- sources -----------------------------------------------------------------------------------------------------
groups, FOC, CBG, ST, V = base_groups()
src = []
for g, ws in groups.items():
    src.append(dict(name=relabel(g), wname=g, kind="focus" if g.startswith("Your wallet") else "coinbase" if g.startswith("Coinbase") else "watched", ws=ws))
ENT = json.load(open(os.path.join(D, "entities_all.json")))["entities"] if os.path.exists(os.path.join(D, "entities_all.json")) else []
for e in ENT:
    ws = {a for a in e["wallets"] if a not in infra}
    if e.get("flagged") or len(ws) < 2 or sum(max(bal[a], 0) for a in ws) < LINKED_MIN: continue
    lead = max(ws, key=lambda a: bal[a])
    src.append(dict(name=f"Linked group {short(lead)}", wname=None, kind="linked", ws=ws))
own, ents = {}, []
for x in src:
    ms = [a for a in x["ws"] if a not in infra and a not in own]
    if not ms: continue
    k = len(ents)
    ents.append(dict(name=x["name"], wname=x["wname"], kind=x["kind"], members=set(ms), attached=[], joined_now=[], capped=False))
    for a in ms: own[a] = k

# ---- stable ids: match each entity to last run's by shared members -----------------------------------------------
prev_ents = prev["entities"] if prev else []
pairs = []
for k, e in enumerate(ents):
    for j, p in enumerate(prev_ents):
        pm = set(p["members"]); o = len(e["members"] & pm)
        if o and (o >= 0.5 * min(len(e["members"]), len(pm)) or (e["wname"] and e["wname"] == p.get("wname"))): pairs.append((o, k, j))
used_k, used_j, match = set(), set(), {}
for o, k, j in sorted(pairs, reverse=True):
    if k in used_k or j in used_j: continue
    used_k.add(k); used_j.add(j); match[k] = j
ids = set()
for k, e in enumerate(ents):
    if k in match:
        p = prev_ents[match[k]]; e["id"] = p["id"]; e["created"] = p["created"]
        for x in p.get("attached", []):                       # joins are kept unless a higher-priority group claims the wallet
            if x["a"] not in own and ok(x["a"]): e["members"].add(x["a"]); own[x["a"]] = k; e["attached"].append(x)
    else:
        lead = max(e["members"], key=lambda a: bal[a]); e["id"] = lead[2:10]
        e["created"] = TODAY if prev else min(first_seen.get(a, NOW) for a in e["members"])[:10]
    while e["id"] in ids: e["id"] += "x"
    ids.add(e["id"])

# ---- follow the coins: attach by seed / drain over the last 90 days ------------------------------------------------
c90, c30 = cut(2160), cut(720)
cand_seed = [(r, s, ts, v, usd) for r, (s, ts, v, usd) in first_in.items() if ts > c90 and usd >= MIN_USD]
cand_drain = [d for d in drains if d[2] > c90]
def attach(k, a, ts, how, frm, v):
    e = ents[k]
    if e["kind"] == "linked" and len(e["members"]) >= CAP: e["capped"] = True; return False
    if len(e["joined_now"]) >= PER_RUN: e["capped"] = True; return False
    rec = dict(a=a, d=ts[:10], how=how, frm=frm, tok=round(v))
    e["members"].add(a); own[a] = k; e["attached"].append(rec); e["joined_now"].append(rec); return True
changed = True
while changed:
    changed = False
    for r, s, ts, v, usd in sorted(cand_seed, key=lambda x: x[2]):
        if r in own or s not in own or not ok(r) or seeds[s] > HUB: continue
        changed |= attach(own[s], r, ts, "seed", s, v)
    for s, r, ts, v, usd in cand_drain:
        for a, b in ((s, r), (r, s)):
            if a in own and b not in own and ok(b) and seeds[a] <= HUB: changed |= attach(own[a], b, ts, "drain", a, v)

# ---- flows by channel, daily net, entity-to-entity edges, provisional receivers ------------------------------------
NW = len(WIN)
W = [[collections.Counter() for _ in range(NW)] for _ in ents]
day0 = datetime.date.fromisoformat(TODAY) - datetime.timedelta(days=90)
dn = [[0.0] * 91 for _ in ents]
edges = [collections.Counter() for _ in range(NW)]
recv = [collections.defaultdict(lambda: [0.0, 0.0, None, None]) for _ in ents]
tw = [collections.Counter() for _ in ents]                     # tripwire sums: since last run, and the 90 days before it
c_prior = iso(parse(since) - datetime.timedelta(days=90))
def node(a):
    if a in own: return ents[own[a]]["id"]
    if is_dex(a): return "D"
    if is_cex(a): return "C"
    if a in LP: return "L"
    if a in (DEAD, NULL): return "B"
    if a == TOKEN: return "T"
    return "O"
for s, r, ts, v, b in T:
    if ts <= c_prior and ts <= c90: continue
    ks, kr = own.get(s), own.get(r)
    if ks is None and kr is None: continue
    if ts > c_prior and ts <= since:
        if ks is not None and ks != kr:
            if is_cex(r): tw[ks]["cexPrior"] += v
            elif is_dex(r): tw[ks]["dexPrior"] += v
    if ts > since and ks is not None and ks != kr:
        if is_cex(r): tw[ks]["cex"] += v
        elif is_dex(r): tw[ks]["dex"] += v
        elif kr is None and r not in LP and r not in (DEAD, TOKEN): tw[ks]["wout"] += v
    if ts <= c90: continue
    age = (now_dt - parse(ts)).total_seconds() / 3600
    di = min(90, max(0, (datetime.date.fromisoformat(ts[:10]) - day0).days))
    keys = []
    if ks is not None and ks == kr: keys.append((ks, "internal"))
    else:
        if ks is not None:
            dn[ks][di] -= v
            keys.append((ks, "dexOut" if is_dex(r) else "cexOut" if is_cex(r) else "entOut" if kr is not None else "othOut" if (r in LP or r in (DEAD, NULL, TOKEN)) else "wOut"))
            if kr is None and ok(r) and ts > c30 and r not in infra:
                x = recv[ks][r]; x[0] += v; x[1] += v * pa(ts); x[2] = x[2] or ts; x[3] = ts
        if kr is not None:
            dn[kr][di] += v
            keys.append((kr, "dexIn" if is_dex(s) else "cexIn" if is_cex(s) else "entIn" if ks is not None else "othIn" if (s in LP or s in (DEAD, NULL, TOKEN)) else "wIn"))
    for wi, Wh in enumerate(WIN):
        if age >= Wh: continue
        for k, key in keys: W[k][wi][key] += v; W[k][wi]["n"] += 1
        if ks != kr: edges[wi][(node(s), node(r))] += v

# ---- cost basis: FIFO over each entity's external flows, full history ----------------------------------------------
lots = [collections.deque() for _ in ents]
cost = [dict(realized=0.0, invested=0.0, proceeds=0.0) for _ in ents]
for k, (s, r, ts, v, b) in enumerate(T):
    ks, kr = own.get(s), own.get(r)
    if ks == kr: continue
    px = PX[k]
    if kr is not None:
        lots[kr].append([v, px, "D" if is_dex(s) else "C" if is_cex(s) else "W"]); cost[kr]["invested"] += v * px
    if ks is not None:
        c = cost[ks]; c["proceeds"] += v * px; q = v; L = lots[ks]
        while q > 1e-9 and L:
            lot = L[0]; t = min(q, lot[0]); c["realized"] += t * (px - lot[1]); lot[0] -= t; q -= t
            if lot[0] <= 1e-9: L.popleft()

# ---- evidence strength (focus cluster): holdings reachable from the focus wallet through direct evidence only ------
FC = json.load(open(os.path.join(D, "focus_cluster.json")))
direct_adj = collections.defaultdict(set)
for m in FC["members"]:
    for ev in m.get("evidence", []):
        if ev["kind"] != "deposit": direct_adj[m["a"]].add(ev["frm"]); direct_adj[ev["frm"]].add(m["a"])

def status(x, b):
    if not x["n"]: return "dormant"
    net = x["dexIn"] + x["cexIn"] + x["wIn"] + x["entIn"] + x["othIn"] - x["dexOut"] - x["cexOut"] - x["wOut"] - x["entOut"] - x["othOut"]
    thr = max(0.0001 * SUPPLY, 0.01 * b)
    if net > thr: return "accumulating"
    if net < -thr:
        out = x["dexOut"] + x["cexOut"] + x["wOut"] + x["entOut"] + x["othOut"]
        if x["cexOut"] >= 0.5 * out: return "distributing"
        if x["dexOut"] + x["cexOut"] >= 0.5 * out: return "selling"
        return "moving"
    return "holding"

out, alerts = [], []
prev_by = {p["id"]: p for p in prev_ents}
first_run = prev is None
def alert(sev, kind, text, **kw): alerts.append(dict(severity=sev, kind=kind, text=text, at=NOW, **kw))
for k, e in enumerate(ents):
    ms = sorted(e["members"]); b = sum(max(bal[a], 0) for a in ms)
    ser = [0.0] * 91; ser[90] = b
    for i in range(90, 0, -1): ser[i - 1] = max(0.0, ser[i] - dn[k][i])
    L = lots[k]; held = sum(l[0] for l in L); chel = sum(l[0] * l[1] for l in L)
    srcq = collections.Counter(); [srcq.update({l[2]: l[0]}) for l in L]
    c = cost[k]
    cb = dict(avg=chel / held if held > 1 else None, costUsd=round(chel), valueUsd=round(held * spot), unreal=round(held * spot - chel),
              realized=round(c["realized"]), invested=round(c["invested"]), proceeds=round(c["proceeds"]),
              src={kk: round(100 * vv / held, 1) for kk, vv in srcq.items()} if held > 1 else {})
    wins = [[round(W[k][wi][ch] / 1e9, 5) if ch != "n" else W[k][wi]["n"] for ch in CH] for wi in range(NW)]
    sts = [status(W[k][wi], b) for wi in range(NW)]
    direct = None
    if e["kind"] == "focus":
        adj = collections.defaultdict(set, {a: set(x) for a, x in direct_adj.items()})
        for x in e["attached"]: adj[x["a"]].add(x["frm"]); adj[x["frm"]].add(x["a"])
        reach, fr = {FOCUS}, [FOCUS]
        while fr:
            fr = [y for a in fr for y in adj[a] if y in e["members"] and y not in reach and not reach.add(y)]
        db = sum(max(bal[a], 0) for a in reach)
        direct = dict(wallets=len(reach), bal=round(db), pct=round(100 * db / b, 1) if b else None)
    fs = min((first_seen.get(a, NOW) for a in ms), default=NOW)[:10]
    la = max((last_seen.get(a, "") for a in ms), default="")[:10]
    net30 = ser[90] - ser[60]
    forming = None
    if b >= 0.001 * SUPPLY:
        if fs >= cut(1440)[:10]: forming = "first GME in the last 60 days"
        elif ser[60] > 0 and net30 >= 0.5 * ser[60]: forming = f"grew {100 * net30 / ser[60]:.0f}% in 30 days"
        elif prev and e["id"] not in prev_by: forming = "new group this run"
    prov = []
    for a, (tok, usd, f, l) in recv[k].items():
        if usd >= MIN_USD and a not in own and bal[a] >= 0.5 * tok:
            prov.append(dict(a=a, recv=round(tok), usd=round(usd), bal=round(max(bal[a], 0)), first=f[:10], last=l[:10]))
    prov.sort(key=lambda x: -x["recv"]); prov = prov[:12]
    rec = dict(id=e["id"], name=e["name"], wname=e["wname"], kind=e["kind"], created=e["created"], n=len(ms), bal=round(b), pct=round(100 * b / SUPPLY, 4),
               series=[round(x / 1e9, 4) for x in ser], w=wins, status=sts, cost=cb, firstSeen=fs, lastActive=la, direct=direct, forming=forming,
               capped=e["capped"], flagged=e["kind"] == "linked" and len(ms) > CAP,
               members=ms, attached=e["attached"], provisional=prov)
    out.append(rec)
    # ---- tripwires since the last run ----
    if not prev: continue
    p = prev_by.get(e["id"]); t = tw[k]; nm = e["name"]
    if e["joined_now"]:
        tot = sum(x["tok"] for x in e["joined_now"])
        alert("medium" if tot >= 0.0005 * SUPPLY else "info", "joined",
              f"{nm}: {len(e['joined_now'])} wallet(s) joined by following the coins ({', '.join(sorted({x['how'] for x in e['joined_now']}))} rule): {tot/1e9:.2f}B moved into them. Counted as the group's own, not as selling.", entity=e["id"])
    if t["cex"] >= 5e7 and t["cexPrior"] == 0:
        alert("high", "first_cex", f"{nm}: first exchange deposit in 90 days, {t['cex']/1e9:.2f}B (~${t['cex']*spot:,.0f}, {100*t['cex']/SUPPLY:.2f}% of supply).", entity=e["id"])
    if t["dex"] >= 5e7 and t["dexPrior"] == 0:
        alert("high" if t["dex"] >= 0.0005 * SUPPLY else "medium", "first_dex_sale", f"{nm}: first DEX sale in 90 days, {t['dex']/1e9:.2f}B (~${t['dex']*spot:,.0f}).", entity=e["id"])
    if t["wout"] >= 0.0005 * SUPPLY:
        alert("medium", "moved_out", f"{nm}: {t['wout']/1e9:.2f}B moved to wallets outside the group since the last run (not a sale; no linking rule ties them to it yet).", entity=e["id"])
    pprov = {x["a"] for x in (p or {}).get("provisional", [])}
    for x in prov:
        if x["a"] not in pprov and x["recv"] >= 0.0005 * SUPPLY:
            alert("medium", "provisional", f"{nm}: {short(x['a'])} received {x['recv']/1e9:.2f}B from it in 30 days and still holds {x['bal']/1e9:.2f}B, but no linking rule fired. Shown as provisional.", entity=e["id"], wallet=x["a"])
    if forming and not (p or {}).get("forming"):
        alert("medium", "forming", f"{nm} is forming: {forming}. Holds {b/1e9:.2f}B ({100*b/SUPPLY:.2f}%) across {len(ms)} wallets.", entity=e["id"])

order = {"high": 0, "medium": 1, "info": 2}
alerts.sort(key=lambda a: order[a["severity"]])
events = (alerts + (prev or {}).get("events", []))[:300]
E = [[[s_, t_, round(v / 1e9, 4)] for (s_, t_), v in sorted(edges[wi].items(), key=lambda kv: -kv[1])[:400] if v >= 1e6] for wi in range(NW)]
out.sort(key=lambda x: -x["bal"])
json.dump(dict(asOf=NOW, since=since, spot=spot, windows=list(WIN), channels=CH, entities=out, edges=E, alerts=alerts, events=events), open(RP, "w"))
att = sum(len(e["joined_now"]) for e in ents)
print(f"entities: {len(out)} ({sum(1 for e in out if e['kind']=='linked')} linked groups) · {sum(e['n'] for e in out)} wallets · {att} joined this run · "
      f"{sum(len(e['provisional']) for e in out)} provisional · {sum(1 for e in out if e['forming'])} forming · {len(alerts)} alerts · since {since}")
for e in out[:6]:
    print(f"  {e['id']:10s} {e['name'][:32]:32s} {e['n']:3d} w {e['bal']/1e9:7.2f}B  7d {e['status'][1]:12s} 30d {e['status'][2]:12s} joined {len(e['attached'])}  prov {len(e['provisional'])}")
