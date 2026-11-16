# The Wallet page's data (#wallet/<address>): paste any address, get its whole GME history and what the terminal knows
# about it. Every non-infrastructure address that ever sent or received GME gets a record:
#   - every transfer: time, signed GME, $ (the exact execution price for a DEX trade found by trades.py, otherwise that
#     day's close), what it was (DEX buy/sale, exchange in/out, liquidity, burn, wallet in/out), counterparty, tx hash;
#   - profit and loss over time (pnl.Book: the same FIFO method as the group charts and the wallet drawer);
#   - links the terminal can show: where its first GME came from, which wallets it seeded, exchange deposit addresses it
#     shares with other wallets, its tracked entity or linked group, strong ETH links (eth_links.json), and its ETH side
#     from the BigQuery study (data/bq/eth_flows.csv) when it is a study wallet;
#   - watch tags (quiet accumulator, buy-and-hide holding wallet, relay, smart money).
# Plus _labels (infrastructure, exchange deposit addresses, ETH-side exchange wallets), _fp (a buying fingerprint per
# wallet, for "bought the same way") and _meta.
#
# Output: data/wallet-index.jsonl.gz (~15 MB), one JSON line per shard of wallets keyed by the 3 hex characters after
# "0x", plus the _labels/_fp/_meta lines. Not committed: the workflow uploads it as a release asset (gme-archive) BEFORE
# the data commit, and build-site.mjs expands it into dist/w/<shard>.json, so the deploy that commit triggers serves it.
import sys, os, json, csv, gzip, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
from venues import deposits, node, LPS
from pnl import Book

ld = lambda name, default: json.load(open(os.path.join(D, name))) if os.path.exists(os.path.join(D, name)) else default
LP = {V3POOL} | LPS                                              # liquidity adds and removals, not trades
SEED_USD = 2000                                                 # the linking rule's bar (cluster_all.py seed)
sec = lambda ts: int(datetime.datetime.fromisoformat(ts[:19]).replace(tzinfo=datetime.timezone.utc).timestamp())
gme = lambda v: round(v) if abs(v) >= 1000 else round(v, 3)
usd = lambda u: round(u) if u >= 1000 else round(u, 2)


def kind(other, out, infra, CEX, DEP):
    """What a transfer is, seen from the wallet: the same rules as terminal.py kind() (the wallet drawer). DEX = any
    infrastructure that is not an exchange, liquidity, the token contract, burn or mint; an exchange deposit address
    counts as the exchange."""
    if other in infra and other not in CEX and other not in LP and other not in (NULL, DEAD, TOKEN): return "s" if out else "b"
    if other in CEX or other in DEP: return "co" if out else "ci"
    if other == TOKEN: return "o" if out else "i"                # a send to the token contract itself is not a sale
    if other in LP: return "la" if out else "lr"
    if other == DEAD: return "x"
    return "o" if out else "i"


def build(T, PX, KEYS, TX, TP, infra, CEX, DEP):
    """One pass over the transfers. Returns per-address rows [ts, signed GME, $, kind, counterparty, tx, log index,
    exact price?], each wallet's first GME (seed), the wallets each address seeded, the users of each exchange deposit
    address, and balances. Infrastructure gets no rows."""
    rows = collections.defaultdict(list)
    seed, seeded, dep_users = {}, collections.defaultdict(list), collections.defaultdict(set)
    bal = collections.Counter()
    for j, (s, r, ts, v, b) in enumerate(T):
        if s == r or v <= 0: continue                            # zero-value transfers are address-poisoning spam
        bal[s] -= v; bal[r] += v
        ex = int(KEYS[j] in TP)
        for me, other, out in ((s, r, True), (r, s, False)):
            if me in infra: continue
            rows[me].append((ts, -v if out else v, v * PX[j], kind(other, out, infra, CEX, DEP), other, TX[j], KEYS[j][1], ex))
        if r not in infra and r not in seed:
            seed[r] = (s, ts, v, v * PX[j])
            if s not in infra: seeded[s].append((r, ts, v, v * PX[j]))
        if r in DEP and s not in infra: dep_users[r].add(s)
    return rows, seed, seeded, dep_users, bal


def group_books(T, PX, gof, infra, CEX, DEP, day0):
    """Profit and loss of each linked group as ONE owner (pnl.Book, as entities.py does for tracked groups): a transfer
    between two of the group's own wallets is internal and skipped; every other transfer touching a member is the
    group buying, selling, receiving or sending. gof: wallet → group id. Returns {group id: {track, marks}}."""
    books = {}
    for j, (s, r, ts, v, b) in enumerate(T):
        if s == r or v <= 0: continue
        gs, gr = gof.get(s), gof.get(r)
        if gs is not None and gs == gr: continue
        if gr is not None:
            k = kind(s, False, infra, CEX, DEP)
            books.setdefault(gr, Book(day0)).inflow(ts, v, PX[j], "D" if k == "b" else "C" if k == "ci" else "W")
        if gs is not None:
            k = kind(r, True, infra, CEX, DEP)
            books.setdefault(gs, Book(day0)).outflow(ts, v, PX[j], "D" if k == "s" else "C" if k == "co" else None)
    return {g: bk.finish() for g, bk in books.items()}


def seeded_lists(sd, DEP, cap=60):
    """Wallets whose first GME came from this one, at the linking rule's $2k bar; exchange deposit addresses are its
    exchange account (shown under exchanges), and smaller first sends (often airdrop spam) are only counted.
    Returns (listed, [more listed beyond cap, small ones])."""
    sd = [x for x in sd if x[0] not in DEP]
    big = [[x, ts_[:16], gme(v_), usd(u_)] for x, ts_, v_, u_ in sd if u_ >= SEED_USD]
    return big[:cap], [len(big) - len(big[:cap]), len(sd) - len(big)]


def eth_side():
    """Study wallets' top-level ETH in and out since 2024-04 (BigQuery), and their first funder with the same guard as
    ethside.py: the first ETH must arrive no later than the wallet's own first transaction."""
    p = os.path.join(D, "bq", "eth_flows.csv")
    if not os.path.exists(p): return {}, set(), None
    W = {r[0] for r in csv.reader(open(os.path.join(D, "bq", "wallets.csv"))) if r and r[0] != "a"}
    ins, outs, own_min, n0_at, first_in = collections.defaultdict(list), collections.defaultdict(list), {}, {}, {}
    through = ""
    for r in csv.DictReader(open(p)):
        f_, t = r["f"].lower(), r["t"].lower(); n, eth = int(r["n"]), float(r["eth"]); fi, la = r["first"][:19], r["last"][:19]
        mn = int(float(r["min_nonce"])) if r.get("min_nonce") not in (None, "") else None
        through = max(through, la)
        if f_ == t: continue
        if t in W:
            ins[t].append((f_, eth, n, fi, la))
            if t not in first_in or fi < first_in[t][1]: first_in[t] = (f_, fi, eth)
        if f_ in W:
            outs[f_].append((t, eth, n, fi, la))
            if mn is not None:
                own_min[f_] = min(own_min.get(f_, mn), mn)
                if mn == 0: n0_at[f_] = min(n0_at.get(f_, fi), fi)
    top = lambda xs: [[a, round(e, 4), n, fi[:10], la[:10]] for a, e, n, fi, la in sorted(xs, key=lambda x: -x[1])[:8]]
    out = {}
    for a in W:
        if a not in ins and a not in outs: continue
        x = dict(inN=len(ins[a]), outN=len(outs[a]), inEth=round(sum(e for _, e, *_ in ins[a]), 4), outEth=round(sum(e for _, e, *_ in outs[a]), 4),
                 top_in=top(ins[a]), top_out=top(outs[a]), fresh=own_min.get(a) == 0 if a in own_min else None)
        if x["fresh"] and a in first_in:
            fa, fi, e = first_in[a]
            x["funder"] = [fa, fi[:16], round(e, 4)] if fi <= n0_at[a] else None     # None = funded some other way
        out[a] = x
    return out, set(ins) | set(outs) | {r[0] for a_ in outs.values() for r in a_} | {r[0] for a_ in ins.values() for r in a_}, through[:10] or None


def main():
    T = load(); pa = prices(); KEYS = load_keys(); TP = trade_px()
    if KEYS is None or len(KEYS) != len(T): KEYS = [(t[4], 0) for t in T]; TP = {}
    PX = [TP.get(k) or pa(T[i][2]) for i, k in enumerate(KEYS)]
    with open(os.path.join(D, "transfers.csv")) as f:             # transaction hashes, aligned with T
        h = next(f).strip().split(",")
        TX = [r[h.index("tx")] for r in csv.reader(f) if r and r[0] != "sender"] if "tx" in h else [""] * len(T)
    assert len(TX) == len(T)
    EX = ld("exclude.json", {}); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
    AT = ld("addr-types.json", {})
    DEP = deposits(T, EX)                                        # exchange deposit address → the exchange wallet it pays
    via = lambda a: "Straight from the pool" if a in (PAIR, V3POOL) else node(a, EX, DEP, AT)[2] or "Other"   # as the group profile
    rows, seed, seeded, dep_users, bal = build(T, PX, KEYS, TX, TP, infra, CEX, DEP)
    day0 = T[0][2][:10]
    # tracked entities (entities.json) and every linked group (entities_all.json, flagged webs included)
    REG = ld("entities.json", {"entities": []})
    ent = {}
    for e in REG["entities"]:
        for a in e["members"]: ent[a] = [e["id"], "m"]
        for x in e.get("attached", []): ent[x["a"]] = [e["id"], "j", x.get("how"), x.get("frm"), x.get("d")]
    ALL = ld("entities_all.json", {"entities": [], "webs": []})
    # every linked group the grouping rules found (cluster_all.py), tracked or not, plus the flagged webs: the Wallet
    # page opens a tracked one as its entity and any other one from _groups (members, evidence, P&L as one owner)
    grp, gof, GROUPS = {}, {}, {}
    for kind_, src in (("group", ALL.get("entities", [])), ("web", ALL.get("webs", []))):
        for g in src:
            ws = [a for a in g["wallets"] if a not in gof]                # a wallet in a group AND a web belongs to the group
            if not ws: continue
            gid = ("w" if kind_ == "web" else "g") + min(g["wallets"])[2:12]
            for a in ws: gof[a] = gid
            mem = sorted(((a, bal[a]) for a in g["wallets"]), key=lambda x: -x[1])
            GROUPS[gid] = dict(kind=kind_, n=g["n"], held=gme(sum(max(b_, 0) for _, b_ in mem)), flagged=kind_ == "web" or g.get("flagged", False),
                               via=g.get("via", {}), name=("Flagged web" if kind_ == "web" else "Linked group") + " " + mem[0][0][-4:],
                               ents=sorted({ent[a][0] for a, _ in mem if a in ent}), members=[[a, gme(b_)] for a, b_ in mem[:300]])
            for a in ws: grp[a] = dict(n=g["n"], held=round(g["held"]), flagged=kind_ == "web" or g.get("flagged", False), via=g.get("via", {}), web=kind_ == "web", gid=gid)
    # one owner's P&L per group (not for webs: a flagged web is not trusted as one owner)
    for gid, pl in group_books(T, PX, {a: g for a, g in gof.items() if g[0] == "g"}, infra, CEX, DEP, day0).items(): GROUPS[gid]["pl"] = pl
    # watch tags
    tags = collections.defaultdict(dict)
    for row in ld("stealth.json", {"rows": []})["rows"]:
        for a in row["wallets"]: tags[a]["acc"] = dict(owner=row["owner"], n=row["n"], net=round(row["net"]), lastBuy=row.get("lastBuy"))
    for a, v in ld("vaults90.json", {}).items(): tags[a]["vault"] = dict(feeders=len(v.get("feeders", [])), tok=round(v["tok"]), first=v["first"][:10])
    for a, v in ld("vaults90_relays.json", {}).items(): tags[a]["relay"] = dict(tok=round(v["tok"]), soldDex=round(v.get("soldDex", 0)), toCex=round(v.get("toCex", 0)))
    for r in ld("crowd.json", {}).get("smart", {}).get("rows", []):
        if r.get("u"): tags[r["u"]]["smart"] = dict(realized=r["realized"], roi=r["roi"])
    WS = ld("watch_state.json", {})
    from groups import namer
    relabel = namer()
    for g, ws in WS.get("members", {}).items():
        for a in ws: tags[a]["watch"] = relabel(g)
    links = collections.defaultdict(list)
    for a, b_, k, d in ld("eth_links.json", {"links": []})["links"]:
        links[a].append([b_, k, d, "o"]); links[b_].append([a, k, d, "i"])   # a sent b ETH ("o" = this wallet sent)
    ETH, eth_addrs, eth_through = eth_side()

    shards, fp, VIA = collections.defaultdict(dict), [], []
    vi = {}
    for a, rs in rows.items():
        bk = Book(day0); bought = buys = 0.0; nb = 0; fb = lb = None; vias = collections.Counter(); tin = mkt_in = oth_in = sold = sent = 0.0
        for ts, dv, u, k, o, tx, li, ex in rs:
            if dv > 0:
                bk.inflow(ts, dv, u / dv if dv else 0, "D" if k == "b" else "C" if k == "ci" else "W")
                tin += dv
                if k in ("b", "ci"): mkt_in += dv
                else: oth_in += dv
                if k == "b":
                    nb += 1; bought += dv; buys += u; vias[via(o)] += dv; fb = fb or ts; lb = ts
            else:
                bk.outflow(ts, -dv, u / -dv if dv else 0, "D" if k == "s" else "C" if k == "co" else None)
                if k in ("s", "co"): sold += -dv
                else: sent += -dv
        pl = bk.finish()
        rec = dict(b=gme(bal[a]), f=rs[0][0][:16], l=rs[-1][0][:16],
                   t=[[sec(ts), gme(dv), usd(u), k, o, tx, li, ex] for ts, dv, u, k, o, tx, li, ex in rs],
                   pl=pl)
        if AT.get(a) in ("contract", "7702"): rec["ty"] = AT[a]
        if a in DEP: rec["dep"] = DEP[a]
        if a in ent: rec["ent"] = ent[a]
        if a in grp: rec["grp"] = grp[a]
        if a in tags: rec["tags"] = tags[a]
        if a in seed: s_, ts_, v_, u_ = seed[a]; rec["seed"] = [s_, ts_[:16], gme(v_), usd(u_)]
        listed, more = seeded_lists(seeded.get(a, []), DEP)
        if listed: rec["seeded"] = listed
        if any(more): rec["seededMore"] = more
        shared = {d: sorted(dep_users[d] - {a})[:20] for d in {o for *_, k, o, _t, _l, _e in rs if o in DEP} if len(dep_users[d]) > 1}
        if shared: rec["shared"] = shared
        if a in links: rec["ethl"] = links[a]
        if a in ETH: rec["eth"] = ETH[a]
        shards[a[2:5]][a] = rec
        if nb:
            v_ = vias.most_common(1)[0][0]
            if v_ not in vi: vi[v_] = len(VIA); VIA.append(v_)
            fp.append([a, sec(fb), sec(lb), nb, gme(bought), usd(buys), vi[v_], round(sold / tin, 3) if tin else 0, round(sent / tin, 3) if tin else 0,
                       round(oth_in / tin, 3) if tin else 0, gme(bal[a]), sec(rs[0][0])])
    # labels: every infrastructure address, every exchange deposit address, ETH-side exchange wallets
    labels = {a: list(node(a, EX, DEP, AT)[1:]) for a in infra}
    labels.update({a: ["deposit", node(a, EX, DEP, AT)[2]] for a in DEP})
    for r in csv.reader(open(os.path.join(D, "eth_labels.csv"))):
        if len(r) >= 2 and r[0].startswith("0x") and r[0].lower() not in labels and r[0].lower() in eth_addrs: labels[r[0].lower()] = ["cex", r[1]]
    chk = ld("trades_check.json", {})
    meta = dict(asOf=T[-1][2], indexedAt=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), day0=day0,
                wallets=len(rows), rows=sum(len(x) for x in rows.values()), exactPct=chk.get("coverageVol"), via=VIA,
                ethThrough=eth_through,
                cols=dict(t=["unix time", "GME (signed)", "$", "kind", "counterparty", "tx", "log index", "exact price"],
                          fp=["address", "first buy", "last buy", "buys", "GME bought", "$ spent", "via", "sold share", "sent share", "other-in share", "balance", "first seen"]))
    out = os.path.join(D, "wallet-index.jsonl.gz")
    with gzip.open(out + ".tmp", "wt", compresslevel=6) as f:
        f.write(json.dumps(dict(k="_meta", d=meta), separators=(",", ":")) + "\n")
        f.write(json.dumps(dict(k="_labels", d=labels), separators=(",", ":")) + "\n")
        f.write(json.dumps(dict(k="_fp", d=fp), separators=(",", ":")) + "\n")
        f.write(json.dumps(dict(k="_groups", d=GROUPS), separators=(",", ":")) + "\n")
        for k in sorted(shards): f.write(json.dumps(dict(k=k, d=shards[k]), separators=(",", ":")) + "\n")
    os.replace(out + ".tmp", out)
    print(f"wallet-index: {len(rows):,} wallets in {len(shards)} shards · {meta['rows']:,} transfer rows · {len(fp):,} buying fingerprints · "
          f"{len(labels):,} labels · {len(GROUPS):,} linked groups · {len(ETH):,} with an ETH side · {os.path.getsize(out) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
