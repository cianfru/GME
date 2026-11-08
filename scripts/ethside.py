# The ETH side of the study, from data/bq/ (BigQuery eth_flows + token_footprint, signers from public nodes):
# who funded the study wallets, ETH links between them, purchases paid for by another wallet, where their ETH comes
# from and goes, and the other tokens they trade. Writes data/ethside.json for the site.
#
# Guards (over-merging overstates control, the cardinal sin):
#   - an exchange never links anyone: labelled hot wallets (eth_labels.csv + exclude.json), any sender whose
#     transaction count (nonce) passed 50,000, any wallet that sent ETH to more than 12 study wallets (the focus
#     wallet excepted: its ETH funding is an existing rule) or received ETH from more than 8 count as a SERVICE;
#   - ETH one way while GME went the other way between the same two wallets looks like an OTC sale: not a link;
#   - a shared first funder links wallets only when it is private and funded 2–8 of them (more = a distributor);
#   - a purchase signed by another wallet links the two only if the GME went straight from a GME pool to the
#     recipient in that transaction (a swap with another wallet named as the recipient) and that signer bought for at
#     most 10 different wallets. Deliveries through settlement, bot, aggregator or bridge contracts are signed by
#     their solvers, relayers or executors, not by the buyer: never a link.
# Evidence grades, strongest first: "ethseed" (A sent B its first ETH) and "gas" (A topped B up with ≤0.05 ETH) are
# DIRECT and STRONG; "eth" (a larger ETH transfer, no GME back) is DIRECT but WEAK (could be a payment); "paid" (A
# signed a swap that delivered GME from a pool straight to B) is WEAK too: most of these signers are trading-bot
# executors that sign for many unrelated buyers (one buyer's purchases signed by up to 17 different executors, one
# executor signing for up to 15 buyers), so a signature alone does not show one owner; "funder" (same private first
# funder) is INFERRED.
# The strong links go to data/eth_links.json. The NEXT run's cluster_all.py and entities.py read it: cluster_all.py
# links wallets through them like a GME seed or drain, and entities.py attaches an unowned wallet to the group of a
# member it is strongly linked to. Weak and inferred links never group wallets; they are only shown as candidates.
import sys, os, csv, json, collections, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *

BQ = os.path.join(D, "bq")
need = os.path.join(BQ, "eth_flows.csv")
if not os.path.exists(need): print("no eth_flows.csv yet"); sys.exit(0)
NONCE_SVC, FANOUT_SVC, FANIN_SVC, MAX_FUND, MAX_PAID, MIN_ETH, GAS_MAX, VOL_SVC = 50_000, 12, 8, 8, 10, 0.001, 0.05, 20_000
MAJORS = {"ETH", "WETH", "USDC", "USDT", "DAI", "WBTC", "STETH", "WSTETH", "USDE", "SUSDE", "FDUSD", "PYUSD", "USDS", "CBBTC", "RETH", "CBETH", "WEETH", "EETH", "TUSD", "BUSD", "LINK", "UNI"}
EX = json.load(open(os.path.join(D, "exclude.json")))
LAB = {a.lower(): n for a, n in csv.reader(open(os.path.join(D, "eth_labels.csv"))) if a.startswith("0x")}
for a, v in EX.items():
    if v.get("kind") == "cex": LAB.setdefault(a, v.get("name", "exchange"))
AT = json.load(open(os.path.join(D, "addr-types.json"))) if os.path.exists(os.path.join(D, "addr-types.json")) else {}
REG = json.load(open(os.path.join(D, "entities.json"))) if os.path.exists(os.path.join(D, "entities.json")) else {"entities": []}
own, ename, ekind = {}, {}, {}
for e in REG["entities"]:
    ename[e["id"]] = e["name"]; ekind[e["id"]] = e["kind"]
    for a in e["members"]: own[a] = e["id"]
W = {r[0]: r[1] for r in csv.reader(open(os.path.join(BQ, "wallets.csv"))) if r and r[0] != "a"}
short = lambda a: a[:6] + "…" + a[-4:]

# ---- ETH flows ----------------------------------------------------------------------------------------------------
pairs = []
with open(need) as f:
    rd = csv.DictReader(f)
    for r in rd:
        pairs.append((r["f"].lower(), r["t"].lower(), int(r["n"]), float(r["eth"]), r["first"][:19], r["last"][:19], int(float(r["min_nonce"])) if r.get("min_nonce") not in (None, "") else None))
maxnonce = collections.Counter(); fanout = collections.defaultdict(set); fanin = collections.defaultdict(set); vol = collections.Counter()
same = lambda x, y: own.get(x) is not None and own.get(x) == own.get(y)    # ETH inside one entity never makes a hub
for f_, t, n, eth, fi, la, mn in pairs:
    vol[f_] += eth; vol[t] += eth
    if mn is not None: maxnonce[f_] = max(maxnonce[f_], mn)
    if t in W and f_ != t and not same(f_, t): fanout[f_].add(t)
    if f_ in W and f_ != t and not same(f_, t): fanin[t].add(f_)
def svc(a):
    if a in LAB: return LAB[a]
    if maxnonce[a] > NONCE_SVC: return f"high-volume sender (nonce >{NONCE_SVC:,})"
    if a in W and vol[a] >= VOL_SVC: return f"moved {vol[a]:,.0f} ETH since 2024-04 (exchange or market-maker scale)"
    if len(fanout[a]) > FANOUT_SVC and a != FOCUS: return f"sent ETH to {len(fanout[a])} study wallets"
    if len(fanin[a]) > FANIN_SVC: return f"received ETH from {len(fanin[a])} study wallets"
    return None
cls = lambda a: ("exchange" if a in LAB else "service") if svc(a) else ("contract" if AT.get(a) == "contract" else "study" if a in W else "private")

# freshness and first funder
# A wallet is fresh when its own first transaction (nonce 0) is in the window. Its first funder is the earliest ETH it
# received, but only if that ETH arrived no later than its first transaction: a wallet cannot pay gas before it has
# ETH, so a "first" transfer that comes later means the real first ETH came some other way (a contract or an exchange
# paying out through an internal transaction, which this table does not hold). 110 of 1,364 wallets were like that
# on 2026-11-08; without this check their later funder was wrongly called their first. It also keeps the weekly
# delta (bq_flows.py) honest: a wallet funded just before the cut-off and first used just after it is not fresh-funded.
own_min, n0_at = {}, {}
for f_, t, n, eth, fi, la, mn in pairs:
    if f_ in W and mn is not None:
        own_min[f_] = min(own_min.get(f_, mn), mn)
        if mn == 0: n0_at[f_] = min(n0_at.get(f_, fi), fi)        # within one pair the lowest nonce is the earliest
first_in = {}
for f_, t, n, eth, fi, la, mn in pairs:
    if t in W and f_ != t and (t not in first_in or fi < first_in[t][1]): first_in[t] = (f_, fi, eth)
fresh = {a for a, m in own_min.items() if m == 0}
funder = {a: first_in[a] for a in fresh if a in first_in and first_in[a][1] <= n0_at[a]}
late_funded = sum(1 for a in fresh if a in first_in and a not in funder)

# ---- links ---------------------------------------------------------------------------------------------------------
T = load(); bal = collections.Counter(); gme_pairs = set()
for s_, r_, ts, v, b in T:
    bal[s_] -= v; bal[r_] += v
    if s_ in W and r_ in W: gme_pairs.add((s_, r_))
links = []; tradelike = 0                                        # (a, b, kind, detail)
for f_, t, n, eth, fi, la, mn in pairs:
    if f_ in W and t in W and f_ != t and eth >= MIN_ETH and not svc(f_) and not svc(t):
        if (t, f_) in gme_pairs: tradelike += 1; continue       # ETH one way, GME the other: looks like a sale
        k = "ethseed" if t in funder and funder[t][0] == f_ else "gas" if eth <= GAS_MAX else "eth"
        links.append((f_, t, k, dict(eth=round(eth, 4), n=n, first=fi[:10], last=la[:10])))
by_funder = collections.defaultdict(list)
for a, (fu, fi, eth) in funder.items():
    if cls(fu) == "private": by_funder[fu].append((a, fi, eth))
distributors = {fu: len(ws) for fu, ws in by_funder.items() if len(ws) > MAX_FUND}
for fu, ws in by_funder.items():
    if 2 <= len(ws) <= MAX_FUND:
        ws = sorted(ws, key=lambda x: x[1])
        for x in ws[1:]: links.append((ws[0][0], x[0], "funder", dict(via=fu, first=x[1][:10])))
SG = os.path.join(BQ, "signers.csv"); paid = []
if os.path.exists(SG):
    seen = set(); rows = []
    for r in csv.DictReader(open(SG)):
        k = (r["tx"], r["recipient"])
        if k not in seen: seen.add(k); rows.append(r)
    want = {r["tx"] for r in rows}; src = {}
    with open(os.path.join(D, "transfers.csv")) as f:
        h = next(f).strip().split(","); ti = h.index("tx")
        for x in csv.reader(f):
            if x[ti] in want: src[(x[ti], x[1])] = (x[0], x[2][:10])
    POOLS = {PAIR, V3POOL}
    allrows = len(rows); rows = [r for r in rows if src.get((r["tx"], r["recipient"]), ("",))[0] in POOLS]
    per_signer = collections.defaultdict(set)
    for r in rows: per_signer[r["signer"]].add(r["recipient"])
    relayers = {s for s, rs in per_signer.items() if len(rs) > MAX_PAID}
    agg = collections.Counter(); firstd = {}
    for r in rows:
        s, rc = r["signer"], r["recipient"]
        if s in relayers or svc(s) or svc(rc): continue
        agg[(s, rc)] += 1; d = src[(r["tx"], rc)][1]; firstd[(s, rc)] = min(firstd.get((s, rc), d), d)
    for (s, rc), n in agg.items(): links.append((s, rc, "paid", dict(n=n, first=firstd[(s, rc)])))
    rc_sig = collections.defaultdict(set)                       # every other wallet that ever signed for this recipient
    for r in csv.DictReader(open(SG)): rc_sig[r["recipient"]].add(r["signer"])
    shared = sum(1 for (s, rc) in agg if len(rc_sig[rc]) > 1)
    paid = dict(signedByOther=allrows, poolDirect=len(rows), relayers=len(relayers), pairs=len(agg), sharedRecipient=shared)

# ---- what the links say about entities ------------------------------------------------------------------------------
unit = lambda a: own.get(a)
uf = {}
def find(x):
    while uf.get(x, x) != x: uf[x] = uf.get(uf[x], uf[x]); x = uf[x]
    return x
def union(a, b): ra, rb = find(a), find(b); uf[ra] = rb if ra != rb else rb
STRONG = ("ethseed", "gas")                                     # the only kinds that group wallets
for a, b, k, d in links:
    if k in STRONG: union(a, b)
cands = collections.defaultdict(lambda: dict(ents=set(), wallets=set(), ev=[]))
for a, b, k, d in links:
    ea, eb = unit(a), unit(b)
    if ea and ea == eb: continue                                 # already in the same entity: confirms, nothing new
    key = tuple(sorted({ea or a, eb or b}))
    c = cands[key]; c["ev"].append(dict(a=a, b=b, kind=k, **d))
    for x, e in ((a, ea), (b, eb)):
        if e: c["ents"].add(e)
        else: c["wallets"].add(x)
def side(x): return dict(id=x, name=ename[x], kind=ekind[x], bal=round(sum(max(bal[a], 0) for a in next(e for e in REG["entities"] if e["id"] == x)["members"]))) if x in ename else dict(a=x, bal=round(max(bal[x], 0)), role=W.get(x))
cand = []
for key, c in cands.items():
    kinds = sorted({e["kind"] for e in c["ev"]})
    cand.append(dict(sides=[side(x) for x in key], kinds=kinds, direct=any(k in STRONG for k in kinds), ev=c["ev"][:12], n=len(c["ev"]),
                     bal=sum(side(x)["bal"] for x in key)))
cand.sort(key=lambda x: (not x["direct"], -x["bal"]))

# ---- money in / out per entity (ETH since 2024-04) --------------------------------------------------------------------
flow = collections.defaultdict(lambda: collections.Counter())
venues_in, venues_out = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
for f_, t, n, eth, fi, la, mn in pairs:
    if f_ == t: continue
    for me, other, dirn in ((t, f_, "in"), (f_, t, "out")):
        if me not in W or svc(me): continue
        u = unit(me) or "unlinked"; oc = cls(other); ou = unit(other)
        if ou and ou == unit(me): continue                       # internal to an entity
        k = {"exchange": "cex", "service": "svc", "contract": "contract", "study": "study", "private": "private"}[oc]
        flow[u][dirn + "_" + k] += eth
        if oc == "exchange": (venues_in if dirn == "in" else venues_out)[u][LAB[other]] += eth
ents_flow = []
for u, c in flow.items():
    ents_flow.append(dict(id=u, name=ename.get(u, "Wallets in no entity"), **{k: round(v, 3) for k, v in c.items()},
                          venuesIn={k: round(v, 3) for k, v in venues_in[u].most_common(4)}, venuesOut={k: round(v, 3) for k, v in venues_out[u].most_common(4)}))
ents_flow.sort(key=lambda x: -(sum(v for k, v in x.items() if isinstance(v, float))))

# funding origin of fresh study wallets
orig = collections.Counter(); orig_v = collections.Counter(); orig_role = collections.defaultdict(collections.Counter)
for a, (fu, fi, eth) in funder.items():
    c = cls(fu)
    k = ("exchange: " + LAB[fu]) if c == "exchange" else ("same entity" if unit(fu) and unit(fu) == unit(a) else c)
    orig[c] += 1
    if c == "exchange": orig_v[LAB[fu]] += 1
    for r in W.get(a, "").split("|"): orig_role[r][c] += 1

# ---- other tokens traded ---------------------------------------------------------------------------------------------
tokens = []
TF = os.path.join(BQ, "token_footprint.csv")
if os.path.exists(TF):
    per_wallet_n = collections.Counter(); rows = []
    for r in csv.DictReader(open(TF)):
        rows.append(r); per_wallet_n[r["a"]] += 1
    busy = {a for a, n in per_wallet_n.items() if n > 300}       # bots or exchange-like wallets: hundreds of tokens
    tk = collections.defaultdict(lambda: dict(owners=set(), wallets=set(), ents=set(), sym="", name="", last=""))
    for r in rows:
        a = r["a"]
        if a in busy or a not in W or svc(a) or int(r["nout"] or 0) == 0: continue    # never sent = usually a spam airdrop
        sym = (r["symbol"] or "").strip()
        plain = unicodedata.normalize("NFKD", sym).encode("ascii", "ignore").decode().upper().strip()
        if not sym or plain != sym.upper() or plain in MAJORS: continue   # majors, and lookalike spam tokens (ĒTH, ЕТН, …)
        x = tk[r["token"]]; x["owners"].add(unit(a) or a); x["wallets"].add(a); x["sym"] = sym; x["name"] = (r["name"] or "")[:40]
        if unit(a): x["ents"].add(unit(a))
        x["last"] = max(x["last"], r["last"][:10])
    for t, x in tk.items():
        if len(x["owners"]) >= 3:
            tokens.append(dict(token=t, symbol=x["sym"], name=x["name"], owners=len(x["owners"]), wallets=len(x["wallets"]), entities=len(x["ents"]),
                               focus=any(ekind.get(e) == "focus" for e in x["ents"]), last=x["last"], ents=sorted(x["ents"])[:12]))
    tokens.sort(key=lambda x: -x["owners"])
    tokens = dict(busyExcluded=len(busy), rows=tokens[:60])

svcw = sorted((a for a in W if svc(a)), key=lambda a: -vol[a])
service_wallets = [dict(a=a, why=svc(a), eth=round(vol[a]), gme=round(max(bal[a], 0)), entity=ename.get(own.get(a)), eid=own.get(a)) for a in svcw[:60]]
svc_ents = sorted({own[a] for a in svcw if own.get(a)})
out = dict(window="2024-04-01", serviceWallets=service_wallets, serviceEntities=[dict(id=e, name=ename[e], n=sum(1 for a in svcw if own.get(a) == e)) for e in svc_ents], wallets=len(W), withFlows=len({a for p_ in pairs for a in p_[:2] if a in W}), fresh=len(fresh), funded=len(funder), lateFunded=late_funded, through=max((p_[5] for p_ in pairs), default='')[:16],
           origin=dict(orig), originVenues=dict(orig_v.most_common(12)), originByRole={k: dict(v) for k, v in orig_role.items()},
           distributors=[dict(a=a, n=n, label=svc(a)) for a, n in sorted(distributors.items(), key=lambda kv: -kv[1])[:20]],
           links={k: sum(1 for l in links if l[2] == k) for k in ("ethseed", "gas", "paid", "eth", "funder")}, tradelike=tradelike, paid=paid,
           candidates=cand[:80], flows=ents_flow[:40], tokens=tokens if isinstance(tokens, dict) else dict(rows=[]),
           rules=dict(volService=VOL_SVC, nonceService=NONCE_SVC, fanoutService=FANOUT_SVC, faninService=FANIN_SVC, maxFund=MAX_FUND, maxPaid=MAX_PAID, minEth=MIN_ETH, gasMax=GAS_MAX))
json.dump(out, open(os.path.join(D, "ethside.json"), "w"))
strong = sorted({(a, b, k, d.get("first", "")) for a, b, k, d in links if k in STRONG and a != b})
json.dump(dict(asOf=max((p_[5] for p_ in pairs), default="")[:10], kinds=list(STRONG), links=[list(x) for x in strong]),
          open(os.path.join(D, "eth_links.json"), "w"), separators=(",", ":"))
print(f"ethside.json: {len(W)} study wallets · {len(fresh)} created since 2024-04, {len(funder)} with a first funder ({late_funded} funded some other way) · origin {dict(orig)} · "
      f"links {out['links']} · {tradelike} OTC-like skipped · {len(svcw)} service-scale studied wallets in {len(svc_ents)} groups · {len(cand)} candidates "
      f"({sum(1 for c in cand if c['direct'])} direct) · {len(out['tokens'].get('rows', []))} shared tokens")
