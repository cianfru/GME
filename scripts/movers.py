# Who is moving GME right now: every holder's activity over the last 24 hours, 7 days and 30 days, grouped by OWNER
# (a tracked entity from entities.json, else an unflagged linked group from entities_all.json, else the wallet itself),
# so moves between one owner's own wallets cancel out. Feeds the Entities page board ("Who's moving"), the entity
# cards ("who moved"), and the Overview panel.
#
# Per window: totals (bought / sold on the DEX, exchange in / out, owners buying / selling, new owners), the owners
# that moved the most (with the wallets that did it), the largest single trades, and an activity series (DEX buys and
# sells and the price, per hour for 24 h, per 6 h for 7 days, per day for 30 days). Per tracked entity and per card
# window (1D/7D/30D/90D): the member wallets that moved, so a card can say who.
#
# $ = the exact execution price for DEX trades matched to a pool swap (trades.py), otherwise that day's close, the same
# as the Wallet page. Transfers under $1 are ignored (dust and spam). Output: data/movers.json (~150 KB).
import sys, os, json, csv, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
from venues import deposits
from wallet_index import kind, ld

WINDOWS = (("24h", 24, 3600), ("7d", 168, 6 * 3600), ("30d", 720, 86400))   # name, hours, bucket seconds
CARD_WIN = (24, 168, 720, 2160)                                              # the entity cards' 1D/7D/30D/90D
TOP_OWNERS, TOP_TRADES, CARD_WALLETS = 60, 40, 6
sec = lambda ts: int(datetime.datetime.fromisoformat(ts[:19]).replace(tzinfo=datetime.timezone.utc).timestamp())
r0 = lambda v: round(v, 4)


def owners(bal):
    """address → (owner key, kind, name). Tracked entities first (members and joined wallets), then unflagged linked
    groups (key = the Wallet page's group id, so the site can open them), else the address."""
    own = {}
    for e in ld("entities.json", {"entities": []})["entities"]:
        for a in e["members"] + [x["a"] for x in e.get("attached", [])]: own[a] = (e["id"], "entity", e["name"])
    for g in ld("entities_all.json", {}).get("entities", []):
        if g.get("flagged"): continue
        gid = "g" + min(g["wallets"])[2:12]
        name = "Linked group " + max(g["wallets"], key=lambda w: bal[w])[-4:]
        for a in g["wallets"]: own.setdefault(a, (gid, "group", name))
    return own


def with_networks(own):
    """An owner-reviewed network (network.py → network.json) counts as ONE owner on the board: its groups' wallets map
    to the network, so GME moving between its groups cancels like moves inside one group."""
    res = dict(own)
    for n in ld("network.json", {"networks": []}).get("networks", []):
        for a in n["members"]: res[a] = (n["id"], "network", n["name"])
    return res


def summarise(rows, own, first, hold_of, t0, t1, bucket):
    """One window: totals, owners, trades and the activity series from per-wallet rows [ts, s, signed GME, $, kind, cp, tx]."""
    O = {}; trades = []; nb = max(1, (t1 - t0 + bucket - 1) // bucket); bars = [[0.0, 0.0, 0.0, 0.0, None, None, None] for _ in range(nb)]
    for a, rs in rows.items():
        key, kd, name = own.get(a, (a, "wallet", ""))
        for ts, s, g, u, k, cp, tx in rs:
            if s < t0: continue
            if own.get(cp, (cp,))[0] == key: continue                    # between one owner's own wallets
            o = O.get(key)
            if not o: o = O[key] = dict(k=key, kind=kd, name=name, f={}, w=collections.defaultdict(lambda: [0.0, 0.0, collections.Counter()]), wallets=set())
            x = o["f"].setdefault(k, [0.0, 0.0, 0]); x[0] += g; x[1] += u; x[2] += 1
            w = o["w"][a]; w[0] += g; w[2][k] += u
            if k in ("b", "s"): w[1] += u
            o["wallets"].add(a)
            j = min(nb - 1, (s - t0) // bucket)
            if k == "b": bars[j][0] += u
            elif k == "s": bars[j][1] += u
            elif k == "ci": bars[j][2] += u
            elif k == "co": bars[j][3] += u
            if k in ("b", "s"):                                        # last, lowest and highest trade price in the bucket
                p = u / abs(g); bars[j][4] = p
                bars[j][5] = p if bars[j][5] is None else min(bars[j][5], p); bars[j][6] = p if bars[j][6] is None else max(bars[j][6], p)
            if k in ("b", "s", "ci", "co") and u >= 50: trades.append([ts[:19] + "Z", a, k, r0(g / 1e9), round(u), tx, key])
    out = []
    for o in O.values():
        f = o["f"]; g = lambda k, i: f.get(k, [0, 0, 0])[i]
        net = sum(v[0] for v in f.values())
        moved = sum(v[1] for kk, v in f.items() if kk in ("b", "s", "ci", "co", "i", "o"))
        if moved < 1: continue
        ws = sorted(o["w"].items(), key=lambda kv: -(abs(kv[1][0]) * 1 + kv[1][1]))
        hold = hold_of.get(o["k"], 0.0)
        fs = first.get(o["k"])
        out.append(dict(k=o["k"], kind=o["kind"], name=o["name"], net=r0(net / 1e9), moved=round(moved),
                        b=[r0(g("b", 0) / 1e9), round(g("b", 1)), g("b", 2)], s=[r0(-g("s", 0) / 1e9), round(g("s", 1)), g("s", 2)],
                        ci=[r0(g("ci", 0) / 1e9), round(g("ci", 1))], co=[r0(-g("co", 0) / 1e9), round(g("co", 1))],
                        i=[r0(g("i", 0) / 1e9), round(g("i", 1))], o=[r0(-g("o", 0) / 1e9), round(g("o", 1))],
                        hold=r0(hold / 1e9), new=bool(fs and sec(fs) >= t0), first=fs[:10] if fs else None,
                        top=[[a, r0(v[0] / 1e9), round(v[1]), v[2].most_common(1)[0][0] if v[2] else ""] for a, v in ws[:4]], nw=len(o["wallets"])))
    tot = dict(buy=round(sum(o["b"][1] for o in out)), sell=round(sum(o["s"][1] for o in out)), buyB=r0(sum(o["b"][0] for o in out)), sellB=r0(sum(o["s"][0] for o in out)),
               buys=sum(o["b"][2] for o in out), sells=sum(o["s"][2] for o in out), buyers=sum(1 for o in out if o["b"][1] >= 1), sellers=sum(1 for o in out if o["s"][1] >= 1),
               cexIn=round(sum(o["ci"][1] for o in out)), cexOut=round(sum(o["co"][1] for o in out)), newOwners=sum(1 for o in out if o["new"] and o["net"] > 0),
               owners=len(out), netBuyers=sum(1 for o in out if o["net"] > 0), netSellers=sum(1 for o in out if o["net"] < 0))
    out.sort(key=lambda o: -o["moved"])
    trades.sort(key=lambda t: -t[4])
    return dict(t0=t0, bucket=bucket, tot=tot, owners=out[:TOP_OWNERS], trades=trades[:TOP_TRADES],
                bars=[[round(b), round(s), round(ci), round(co), p, lo, hi] for b, s, ci, co, p, lo, hi in bars])


def card_movers(rows, own, kinds, t1):
    """Per tracked entity (or network) and card window: its wallets that moved GME in or out of it, largest first."""
    res = {}
    for a, rs in rows.items():
        key, kd, _ = own.get(a, (a, "wallet", ""))
        if kd not in kinds: continue
        for wi, h in enumerate(CARD_WIN):
            t0 = t1 - h * 3600; net = 0.0; u_ = 0.0; ks = collections.Counter()
            for ts, s, g, u, k, cp, tx in rs:
                if s < t0 or own.get(cp, (cp,))[0] == key: continue
                net += g; u_ += u; ks[k] += u
            if u_ >= 1:
                res.setdefault(key, [[] for _ in CARD_WIN])[wi].append([a, r0(net / 1e9), round(u_), ks.most_common(1)[0][0]])
    for key, ws in res.items():
        for wi in range(len(CARD_WIN)): ws[wi] = sorted(ws[wi], key=lambda x: -x[2])[:CARD_WALLETS]
    return res


def main():
    T = load(); pa = prices(); KEYS = load_keys(); TP = trade_px()
    if KEYS is None or len(KEYS) != len(T): KEYS = [(t[4], 0) for t in T]; TP = {}
    PX = [TP.get(k) or pa(T[i][2]) for i, k in enumerate(KEYS)]
    with open(os.path.join(D, "transfers.csv")) as f:
        h = next(f).strip().split(",")
        TX = [r[h.index("tx")] for r in csv.reader(f) if r and r[0] != "sender"] if "tx" in h else [""] * len(T)
    EX = ld("exclude.json", {}); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
    DEP = deposits(T, EX)
    t1 = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    since = t1 - 2160 * 3600
    bal = collections.Counter(); first = {}; rows = collections.defaultdict(list)
    day0 = datetime.datetime.fromtimestamp(since, datetime.timezone.utc).strftime("%Y-%m-%d")
    for j, (s, r, ts, v, b) in enumerate(T):
        if s == r or v <= 0: continue
        bal[s] -= v; bal[r] += v
        if r not in first: first[r] = ts
        if ts[:10] < day0: continue
        st = sec(ts); u = v * PX[j]
        if st < since or u < 1: continue
        for me, other, out in ((s, r, True), (r, s, False)):
            if me in infra or me in DEP: continue                     # pools, routers, exchanges and their deposit addresses
            rows[me].append((ts, st, -v if out else v, u, kind(other, out, infra, CEX, DEP), other, TX[j]))
    own_e = owners(bal); own = with_networks(own_e)
    hold_of, first_of = collections.Counter(), {}                   # per owner: all its wallets, not only the ones that moved
    for a, b in bal.items():
        if b > 0 and a not in infra and a not in DEP: hold_of[own.get(a, (a,))[0]] += b
    for a, f in first.items():
        k = own.get(a, (a,))[0]
        if k not in first_of or f < first_of[k]: first_of[k] = f
    W = {name: summarise(rows, own, first_of, hold_of, t1 - h * 3600, t1, bucket) for name, h, bucket in WINDOWS}
    lastPx = next((PX[j] for j in range(len(T) - 1, -1, -1) if KEYS[j] in TP), PX[-1])
    res = dict(asOf=datetime.datetime.fromtimestamp(t1, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), lastTransfer=T[-1][2], price=lastPx,
               windows=W, ent={**card_movers(rows, own_e, ("entity",), t1), **card_movers(rows, own, ("network",), t1)}, cardWin=list(CARD_WIN))
    json.dump(res, open(os.path.join(D, "movers.json"), "w"), separators=(",", ":"))
    # The public board (the public site's bundle): the same windows with no attribution to fbb4, its network's groups or
    # the linked web they came from. Those wallets appear as plain wallets; every other owner is unchanged.
    priv = set()
    for n in ld("network.json", {"networks": []}).get("networks", []):
        priv |= set(n["members"]) | {w[0] for w in (n.get("map") or {}).get("wallets", [])}
    for e in ld("entities.json", {"entities": []})["entities"]:
        ms = e["members"] + [x["a"] for x in e.get("attached", [])]
        if e["kind"] == "focus" or priv & set(ms): priv |= set(ms)
    own_p = {a: v for a, v in own_e.items() if a not in priv}
    hold_p, first_p = collections.Counter(), {}
    for a, b in bal.items():
        if b > 0 and a not in infra and a not in DEP: hold_p[own_p.get(a, (a,))[0]] += b
    for a, f in first.items():
        k = own_p.get(a, (a,))[0]
        if k not in first_p or f < first_p[k]: first_p[k] = f
    Wp = {name: summarise(rows, own_p, first_p, hold_p, t1 - h * 3600, t1, bucket) for name, h, bucket in WINDOWS}
    json.dump(dict(asOf=res["asOf"], lastTransfer=res["lastTransfer"], price=lastPx, windows=Wp, ent=card_movers(rows, own_p, ("entity",), t1), cardWin=list(CARD_WIN)),
              open(os.path.join(D, "movers_public.json"), "w"), separators=(",", ":"))
    w = W["24h"]["tot"]
    print(f"movers.json: 24h buys ${w['buy']:,} by {w['buyers']} owners, sells ${w['sell']:,} by {w['sellers']} · "
          f"7d {W['7d']['tot']['owners']} owners moved · {len(res['ent'])} entities with movers · "
          f"{os.path.getsize(os.path.join(D, 'movers.json')) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
