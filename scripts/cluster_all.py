# Link wallets across ALL GME holders with the same conservative rules used for the focus cluster:
#   seed  — B had never held GME and A gave it its first GME (≥ MIN_USD at the day's price)
#   drain — A sent ≥90% of its balance to B in one transfer (≥ MIN_USD)
#   deposit — both sent GME to the same exchange deposit address (2–10 depositors)
#   ethseed / gas — the strong ETH links of the last ethside.py run (data/eth_links.json): A sent B its first ETH,
#             or A topped B up with ≤0.05 ETH. ethside.py already drops exchanges, services, relayers and OTC-like pairs.
# Guards: a wallet that seeds >40 wallets is a distributor (no linking through it); nothing links through
# infrastructure, exchange deposit addresses or contracts; groups >60 wallets are flagged.
# Each group lists how many links of each kind hold it together ("via").
#
# Splitting a flagged web (2026-11-08). The one group over 60 wallets was fbb4's looser web: 180 wallets, 86.7B, of
# which 60 are fbb4's own. It is mostly a tree (116 of its 262 links are the only link between two parts), so cutting
# at single links would scatter it into 103 lone wallets and break fbb4's core apart. Instead, a web that contains
# wallets of the groups built by their own scripts (fbb4 = focus_cluster.json and its joins, the Coinbase group) has
# those wallets set aside, and what stays linked among the rest becomes groups of its own: e.g. the #2 holder's
# 13-wallet network, which touches fbb4 by two drains only. Each such group records the links that tie it to the
# set-aside group ("near"); they are shown, never merged, because a few transfers between two networks can be a trade
# as easily as a shared owner. The web itself is kept under "webs" (float.py still counts it as fbb4's looser
# extension, an upper bound), with the lone wallets that hang straight off the known group.
import sys, json, collections, os
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
MIN_USD = 2000; HUB = 40
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
out_to = collections.defaultdict(lambda: collections.defaultdict(float)); in_from = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: out_to[s][r] += v; in_from[r][s] += v
deposit = set()
for a, o in out_to.items():
    if a in infra: continue
    tot = sum(o.values()); cx = sum(v for k, v in o.items() if k in CEX)
    if tot > 0 and cx / tot >= 0.95: deposit.add(a)
edges = []
bal = collections.defaultdict(float); seen = set()
for s, r, ts, v, b in T:
    if s not in infra and r not in infra and s != r and s not in deposit and r not in deposit:
        usd = v * pa(ts)
        if usd >= MIN_USD:
            if r not in seen: edges.append((s, r, "seed", ts[:10]))
            elif bal[s] > 0 and v >= 0.9 * bal[s]: edges.append((s, r, "drain", ts[:10]))
    bal[s] -= v; bal[r] += v; seen.add(r)
for d in deposit:
    deps = [k for k in in_from[d] if k not in infra and k not in deposit]
    if 2 <= len(deps) <= 10:
        for k in deps[1:]: edges.append((deps[0], k, "deposit", ""))
AT = json.load(open(os.path.join(D, "addr-types.json"))) if os.path.exists(os.path.join(D, "addr-types.json")) else {}
EL = os.path.join(D, "eth_links.json")
n_eth = 0
if os.path.exists(EL):
    for a, b, k, d in json.load(open(EL))["links"]:
        if any(x in infra or x in deposit or AT.get(x) == "contract" for x in (a, b)): continue
        edges.append((a, b, k, d)); n_eth += 1
seedout = collections.Counter(s for s, r, k, d in edges if k == "seed")
hubs = {a for a, n in seedout.items() if n > HUB}
parent = {}
def find(a):
    while parent.get(a, a) != a:
        parent[a] = parent.get(parent[a], parent[a]); a = parent[a]
    return a
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb
kept = [e for e in edges if e[0] not in hubs and e[1] not in hubs]
for s, r, k, d in kept: parent.setdefault(s, s); parent.setdefault(r, r); union(s, r)
groups = collections.defaultdict(set); via_root = collections.defaultdict(collections.Counter)
for a in parent: groups[find(a)].add(a)
for s_, r_, k, d in kept: via_root[find(s_)][k] += 1
FOC = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
CBG = {r["a"] for r in json.load(open(os.path.join(D, "coinbase_group.json")))} | {"0xe1fc21df6bbe9caa933f93896866501375669717"}
CAP = 60
# the groups built by their own scripts, with the wallets the registry has joined to them (entities.py keeps joins)
KNOWN = {a: "focus" for a in FOC}
for a in CBG: KNOWN.setdefault(a, "coinbase")
RP = os.path.join(D, "entities.json")
if os.path.exists(RP):
    for e in json.load(open(RP)).get("entities", []):
        if e.get("kind") in ("focus", "coinbase"):
            for a in e["members"]: KNOWN.setdefault(a, e["kind"])


def components(ws):
    """Groups of ws that stay linked using only links between wallets of ws."""
    nb = collections.defaultdict(set)
    for s_, r_, k, d in kept:
        if s_ in ws and r_ in ws: nb[s_].add(r_); nb[r_].add(s_)
    seen_, out = set(), []
    for a in sorted(ws):
        if a in seen_: continue
        st, c = [a], {a}; seen_.add(a)
        while st:
            u = st.pop()
            for v in nb[u]:
                if v not in seen_: seen_.add(v); c.add(v); st.append(v)
        out.append(c)
    return out


def via_of(ws):
    return dict(collections.Counter(k for s_, r_, k, d in kept if s_ in ws and r_ in ws))


ents, webs = [], []
def emit(g, via, **extra):
    ents.append(dict(wallets=sorted(g), n=len(g), held=sum(max(bal[a], 0) for a in g), focus=len(g & FOC), cb=len(g & CBG),
                     flagged=len(g) > CAP, via=dict(via), **extra))
for root, g in groups.items():
    if len(g) < 2: continue
    known = {a for a in g if a in KNOWN}
    if len(g) <= CAP or not known: emit(g, via_root[root]); continue
    rest = g - known; loose = set()
    pieces = [c for c in components(rest) if len(c) >= 2]
    for c in pieces:
        near = collections.defaultdict(collections.Counter)
        for s_, r_, k, d in kept:
            if s_ in c and r_ in known: near[KNOWN[r_]][k] += 1
            elif r_ in c and s_ in known: near[KNOWN[s_]][k] += 1
        emit(c, via_of(c), near={o: dict(x) for o, x in near.items()}, splitFrom=len(g))
    loose = rest - set().union(*pieces) if pieces else rest
    webs.append(dict(wallets=sorted(g), n=len(g), held=sum(max(bal[a], 0) for a in g), setAside=dict(collections.Counter(KNOWN[a] for a in known)),
                     pieces=len(pieces), piecesHeld=sum(max(bal[a], 0) for c in pieces for a in c), loose=sorted(loose),
                     looseHeld=sum(max(bal[a], 0) for a in loose), via=dict(via_root[root])))
ents.sort(key=lambda e: -e["held"])
json.dump(dict(hubs=sorted(hubs), entities=ents, webs=webs), open(os.path.join(D, "entities_all.json"), "w"))
print(f"{len(ents)} multi-wallet groups · {sum(e['n'] for e in ents)} wallets · hubs dropped {len(hubs)} · {n_eth} strong ETH links used · "
      f"{sum(1 for e in ents if any(k in e['via'] for k in ('ethseed', 'gas')))} groups hold one")
for w in webs:
    print(f"web of {w['n']} wallets ({w['held']/1e9:.1f}B): set aside {w['setAside']} · {w['pieces']} groups of their own holding "
          f"{w['piecesHeld']/1e9:.2f}B · {len(w['loose'])} lone wallets hanging off the known group ({w['looseHeld']/1e9:.2f}B)")
for e in ents[:25]:
    top = max(e["wallets"], key=lambda a: bal[a])
    print(f"{e['n']:4d} wallets  {e['held']/1e9:6.2f}B ({100*e['held']/SUPPLY:4.2f}%)  focus-overlap {e['focus']:3d}  coinbase-overlap {e['cb']:2d}  {'FLAGGED' if e['flagged'] else ''}  largest {top} {bal[top]/1e9:.2f}B")
