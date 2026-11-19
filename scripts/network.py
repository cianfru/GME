# Owner-reviewed networks (data/networks.json): groups the grouping rules keep apart but a human reading of the
# evidence treats as one bloc — today the "fbb4 network" (fbb4 + a8c8 + dcf4 + 019d + 5b69). The rules themselves stay
# conservative and unchanged; this only adds a view on top of the registry (entities.py → entities.json).
#
# Per network, recomputed every run with the registry's own methods so it reads like an entity card:
#   - holdings, % of supply, the 90-day series (the members' series added up), first seen / last active;
#   - flows by channel over 1/7/30/90 days (entities.py's channels) with every move BETWEEN its groups internal, and a
#     status per window (entities.py's rule);
#   - cost basis and P&L as ONE owner (pnl.Book, DEX sales and exchange deposits realize, moves between its groups
#     skipped); the day-by-day track goes into pnl.json under the network's id, so the page's P&L drawer opens it;
#   - the evidence between its groups, recomputed from the chain: GME transfers (per pair, with the largest), ETH
#     transfers (BigQuery study flows), shared wallets (a wallet that received GME from two or more of its groups
#     other than its own, and where those coins went next) and shared exchange deposit addresses.
# Output: data/network.json (in site.json as NET). A group that can no longer be found (id gone, anchor in no entity)
# is reported as missing, never guessed.
import sys, os, json, csv, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
from pnl import Book

WIN = (24, 168, 720, 2160)
CH = ["dexIn", "dexOut", "cexIn", "cexOut", "wIn", "wOut", "entIn", "entOut", "othIn", "othOut", "internal", "n"]
LP = {V3POOL, "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
ld = lambda name, default: json.load(open(os.path.join(D, name))) if os.path.exists(os.path.join(D, name)) else default
parse = lambda ts: datetime.datetime.fromisoformat(ts[:19])


def status(x, b):
    """entities.py's rule, unchanged."""
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


def resolve(conf, ents):
    """Network groups → registry entities, by id, else by the entity whose wallets include the anchor."""
    by_id = {e["id"]: e for e in ents}
    of = {}
    for e in ents:
        for a in e["members"] + [x["a"] for x in e.get("attached", [])]: of[a] = e
    found, missing = [], []
    for g in conf["groups"]:
        e = by_id.get(g["id"]) or of.get(g.get("anchor", ""))
        (found if e else missing).append(e or g)
    return found, missing


def evidence(T, PX, TX, gof, labels, deplike, cexw, eth_rows, names):
    """Everything between the network's groups. gof: wallet → group id."""
    gme = collections.defaultdict(lambda: dict(usd=0.0, gme=0.0, n=0, first=None, last=None, top=[]))
    recv = collections.defaultdict(lambda: collections.defaultdict(float))     # wallet → sender group → $
    users = collections.defaultdict(set)                                       # deposit address → groups paying into it
    for j, (s, r, ts, v, b) in enumerate(T):
        if v <= 0 or s == r: continue
        gs, gr = gof.get(s), gof.get(r)
        if gs and gr and gs != gr:
            x = gme[(gs, gr)]; u = v * PX[j]; x["usd"] += u; x["gme"] += v; x["n"] += 1; x["first"] = x["first"] or ts[:10]; x["last"] = ts[:10]
            x["top"].append([ts[:16], s, r, round(v / 1e9, 4), round(u), TX[j] if j < len(TX) else ""])
        if gs and r not in labels and r not in deplike and gs != gr: recv[r][gs] += v * PX[j]
        if gs and r in deplike: users[r].add(gs)
    pairs = []
    for (a, b), x in gme.items():
        x["top"] = sorted(x["top"], key=lambda t: -t[4])[:5]
        pairs.append(dict(kind="gme", a=a, b=b, usd=round(x["usd"]), gme=round(x["gme"] / 1e9, 4), n=x["n"], first=x["first"], last=x["last"], top=x["top"]))
    eth = collections.defaultdict(lambda: dict(eth=0.0, n=0, first=None, last=None, top=[]))
    for r in eth_rows:
        gs, gr = gof.get(r["f"]), gof.get(r["t"])
        if gs and gr and gs != gr:
            x = eth[(gs, gr)]; e = float(r["eth"]); x["eth"] += e; x["n"] += int(r["n"])
            x["first"] = min(x["first"] or r["first"][:10], r["first"][:10]); x["last"] = max(x["last"] or "", r["last"][:10])
            x["top"].append([r["f"], r["t"], round(e, 4), int(r["n"]), r["first"][:10], r["last"][:10]])
    for (a, b), x in eth.items():
        pairs.append(dict(kind="eth", a=a, b=b, eth=round(x["eth"], 4), n=x["n"], first=x["first"], last=x["last"], top=sorted(x["top"], key=lambda t: -t[2])[:5]))
    # shared wallets: received GME from 2+ of the network's groups other than its own, and where it sent GME next
    shared = []
    for w, src in recv.items():
        others = {g: u for g, u in src.items() if g != gof.get(w)}
        if len(others) < 2: continue
        out = collections.Counter()
        for j, (s, r, ts, v, b) in enumerate(T):
            if s == w and v > 0 and s != r:
                out["exchange" if r in cexw or r in deplike else "DEX" if r in labels else names.get(gof.get(r), "network") if gof.get(r) else "other wallets"] += v * PX[j]
        shared.append(dict(a=w, group=gof.get(w), senders={g: round(u) for g, u in sorted(others.items(), key=lambda kv: -kv[1])}, out={k: round(u) for k, u in out.most_common()}))
    shared.sort(key=lambda x: -sum(x["senders"].values()))
    deps = [dict(a=d, groups=sorted(gs)) for d, gs in users.items() if len(gs) >= 2]
    pairs.sort(key=lambda p: (p["kind"] != "gme", -(p.get("usd") or 0), -(p.get("eth") or 0)))
    return dict(pairs=pairs, shared=shared, deposits=deps)


def main():
    conf = ld("networks.json", {"networks": []})
    REG = ld("entities.json", None)
    if not REG or not conf["networks"]:
        json.dump(dict(networks=[]), open(os.path.join(D, "network.json"), "w")); print("network.json: no networks"); return
    ents = REG["entities"]
    T = load(); pa = prices(); PX = exact_prices(T, pa)
    with open(os.path.join(D, "transfers.csv")) as f:
        h = next(f).strip().split(",")
        TX = [r[h.index("tx")] for r in csv.reader(f) if r and r[0] != "sender"] if "tx" in h else []
    EX = ld("exclude.json", {}); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
    outs = collections.defaultdict(lambda: collections.defaultdict(float)); bal = collections.Counter(); first = {}; last = {}
    for s, r, ts, v, b in T:
        outs[s][r] += v; bal[s] -= v; bal[r] += v; first.setdefault(r, ts); first.setdefault(s, ts); last[s] = ts; last[r] = ts
    deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(x for k, x in o.items() if k in CEX) / sum(o.values()) >= 0.95}
    is_dex = lambda a: a in infra and a not in CEX and a not in LP and a not in (NULL, DEAD, TOKEN)
    is_cex = lambda a: a in CEX or a in deplike
    ent_of = {}
    for e in ents:
        for a in e["members"] + [x["a"] for x in e.get("attached", [])]: ent_of[a] = e["id"]
    eth_rows = list(csv.DictReader(open(os.path.join(D, "bq", "eth_flows.csv")))) if os.path.exists(os.path.join(D, "bq", "eth_flows.csv")) else []
    NOW = T[-1][2]; now_dt = parse(NOW); TODAY = NOW[:10]; spot = pa(NOW)
    PNL = ld("pnl.json", None)
    out = []
    for net in conf["networks"]:
        groups, missing = resolve(net, ents)
        gof = {}
        for e in groups:
            for a in e["members"] + [x["a"] for x in e.get("attached", [])]: gof[a] = e["id"]
        mine = set(gof)
        # flows by channel, 1/7/30/90 days, moves between its own wallets (any of its groups) internal
        W = [collections.Counter() for _ in WIN]; bk = Book(T[0][2][:10])
        c90 = (now_dt - datetime.timedelta(hours=WIN[-1])).strftime("%Y-%m-%dT%H:%M:%SZ")
        for j, (s, r, ts, v, b) in enumerate(T):
            ins, inr = s in mine, r in mine
            if not ins and not inr: continue
            if not (ins and inr):
                if inr: bk.inflow(ts, v, PX[j], "D" if is_dex(s) else "C" if is_cex(s) else "W")
                if ins: bk.outflow(ts, v, PX[j], "D" if is_dex(r) else "C" if is_cex(r) else None)
            if ts <= c90: continue
            age = (now_dt - parse(ts)).total_seconds() / 3600
            if ins and inr: keys = ["internal"]
            else:
                o = r if ins else s
                k = ("dex" if is_dex(o) else "cex" if is_cex(o) else "ent" if o in ent_of else "oth" if (o in LP or o in (DEAD, NULL, TOKEN)) else "w") + ("Out" if ins else "In")
                keys = [k]
            for wi, Wh in enumerate(WIN):
                if age < Wh:
                    for k in keys: W[wi][k] += v
                    W[wi]["n"] += 1
        b = sum(max(bal[a], 0) for a in mine)
        ser = [round(sum(e["series"][i] for e in groups), 4) for i in range(91)]
        held, chel = bk.hold, bk.cost
        cost = dict(avg=chel / held if held > 1 else None, costUsd=round(chel), valueUsd=round(held * spot), unreal=round(held * spot - chel),
                    realized=round(bk.realized), invested=round(bk.bought), proceeds=round(bk.sold), src=bk.source_mix())
        names = {e["id"]: e["name"] for e in groups}
        ev = evidence(T, PX, TX, gof, infra, deplike, CEX, eth_rows, names)
        lead = next((e for e in groups if e["id"] == net.get("lead")), groups[0] if groups else None)
        members = sorted(mine, key=lambda a: -bal[a])
        rec = dict(id=net["id"], name=net["name"], tag=(lead or {}).get("tag", ""), kind="network", anchor=(lead or {}).get("anchor"), lead=(lead or {}).get("id"),
                   decided=net.get("decided"), why=net.get("why"), groups=[e["id"] for e in groups], missing=[g.get("tag") or g.get("id") for g in missing],
                   n=len(mine), bal=round(b), pct=round(100 * b / SUPPLY, 4), series=ser,
                   w=[[round(W[wi][ch] / 1e9, 5) if ch != "n" else W[wi]["n"] for ch in CH] for wi in range(len(WIN))],
                   status=[status(W[wi], b) for wi in range(len(WIN))], cost=cost,
                   firstSeen=min((first[a] for a in mine if a in first), default=NOW)[:10], lastActive=max((last[a] for a in mine if a in last), default="")[:10],
                   members=members, attached=[], provisional=[], via=None, near=None, forming=None, flagged=False, capped=False, direct=None,
                   evidence=ev)
        out.append(rec)
        if PNL is not None: PNL["ents"][net["id"]] = bk.finish()
    json.dump(dict(asOf=NOW, spot=spot, windows=list(WIN), channels=CH, networks=out), open(os.path.join(D, "network.json"), "w"), separators=(",", ":"))
    if PNL is not None: json.dump(PNL, open(os.path.join(D, "pnl.json"), "w"), separators=(",", ":"))
    for r in out:
        print(f"network.json: {r['name']} = {len(r['groups'])} groups{' (missing: ' + ', '.join(r['missing']) + ')' if r['missing'] else ''}, {r['n']} wallets, "
              f"{r['bal']/1e9:.2f}B ({r['pct']:.2f}%), 30D {r['status'][2]}, evidence: {sum(1 for p in r['evidence']['pairs'] if p['kind'] == 'gme')} GME pairs, "
              f"{sum(1 for p in r['evidence']['pairs'] if p['kind'] == 'eth')} ETH pairs, {len(r['evidence']['shared'])} shared wallets, {len(r['evidence']['deposits'])} shared deposits")


if __name__ == "__main__":
    main()
