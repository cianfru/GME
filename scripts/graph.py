# The Visualizer's data: every GME transfer since launch, aggregated per directed pair and per calendar month.
#   data/graph.json    — the graph itself, fetched only by the Visualizer page (#visualizer).
#   data/graph_tx.json — the ledger: individual transfers behind the graph, fetched only when the ledger is opened.
#
# Nodes are wallets plus named venues. Infrastructure is collapsed into venues so the graph stays readable:
#   - DEX: the Uniswap pools, Uniswap's routers, 1inch, 0x, CoW and other aggregators each become one node
#     ("Uniswap V2 · GME/WETH", "Uniswap app", "1inch"…); unnamed routers and bots go to "Other routers & bots";
#   - exchanges: one node per labelled exchange wallet (exclude.json kind cex);
#   - exchange deposit addresses (an address that forwarded ≥95% of its GME to an exchange) stay individual nodes,
#     labelled with the exchange they pay into, because two wallets sharing one is the "shared deposit" evidence;
#   - burn, mint and the token contract are one node each; liquidity (V3 positions) is one node.
# Each wallet carries its balance today, the group (entity) it belongs to and whether it is a contract.
# Edges: [from, to, [month, GME (B), $, transfers], …] with month 0 = the launch month (May 2024). $ uses the exact
# execution price for DEX trades (trades.py) and the day's close for everything else. Pairs worth less than MIN_USD in
# total are dropped (dust and address-poisoning spam).
#
# The ledger answers "which transfers is this edge made of", the one thing the monthly aggregate cannot. Keeping every
# transfer would be ~7 MB gzipped committed on every full run, so it keeps the LEDGER_K largest transfers BY VALUE for
# each node (a union, so both ends of a transfer keep it, and every node has a ledger however small it is). Each row
# carries (block, logIndex) rather than the transaction hash: it is the canonical identifier of a Transfer log, it is
# what txlib.load_keys() already aligns on, and the hashes alone would be 2.7x the rest of the file.
import sys, json, os, collections, datetime, heapq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *

MIN_USD = 25.0
LEDGER_K = 12                                                     # largest transfers kept per node for the ledger
T = load(); pa = prices(); PX = exact_prices(T, pa); KEYS = load_keys()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
AT = json.load(open(os.path.join(D, "addr-types.json"))) if os.path.exists(os.path.join(D, "addr-types.json")) else {}
REG = json.load(open(os.path.join(D, "entities.json"))) if os.path.exists(os.path.join(D, "entities.json")) else {"entities": []}

from venues import deposits, node
deposit = deposits(T, EX)
node_of = lambda a: node(a, EX, deposit, AT)

day0 = datetime.date.fromisoformat(T[0][2][:10])
month = lambda ts: (int(ts[:4]) - day0.year) * 12 + int(ts[5:7]) - day0.month
pairs = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0, 0]))
meta = {}
bal = collections.Counter()
legs = []                                                         # (node pair, transfer index, GME, $) for the ledger
for k, (s, r, ts, v, b) in enumerate(T):
    bal[s] -= v; bal[r] += v
    if s == r: continue
    ns, nr = node_of(s), node_of(r)
    if ns[0] == nr[0]: continue
    meta.setdefault(ns[0], ns); meta.setdefault(nr[0], nr)
    u = v * PX[k]
    x = pairs[(ns[0], nr[0])][month(ts)]; x[0] += v; x[1] += u; x[2] += 1
    if u >= 1: legs.append(((ns[0], nr[0]), k, v, u))
keep = {p: m for p, m in pairs.items() if sum(x[1] for x in m.values()) >= MIN_USD}

# Stable order. graph.json is committed every day and the ledger addresses nodes by index, so an order that changes
# daily (by balance, say) rewrites both files completely. Nodes and entities keep their position from the previous
# graph.json; new ones are appended (nodes in order of first appearance). Only nodes that leave the graph shift the
# ones after them, which is rare: a pair's total only grows.
prev = {"nodes": [], "entities": []}
if os.path.exists(os.path.join(D, "graph.json")):
    try: prev = json.load(open(os.path.join(D, "graph.json")))
    except ValueError: pass
def stable(old, new):
    ns = set(new); keep_ = [k for k in old if k in ns]; have = set(keep_)
    return keep_ + [k for k in new if k not in have]
REGE = {e["id"]: e for e in REG.get("entities", [])}
ent_of, ents = {}, []
for i, eid in enumerate(stable([e[0] for e in prev.get("entities", [])], list(REGE))):
    e = REGE[eid]
    ents.append([e["id"], e["name"], e.get("tag", ""), e["kind"], round(e["bal"] / 1e9, 4), e["n"]])
    for a in e["members"]: ent_of[a] = i
want = {a for p in keep for a in p}
used = stable([n[0] for n in prev.get("nodes", [])], [a for a in meta if a in want])     # meta is in first-appearance order
ix = {a: i for i, a in enumerate(used)}
KC = {"wallet": 0, "contract": 1, "deposit": 2, "cex": 3, "dex": 4, "lp": 5, "burn": 6, "mint": 7, "token": 8}
vbal = collections.Counter()                                      # venue balances (sum of their addresses, e.g. the pools)
for a, v in bal.items():
    k = node_of(a)[0]
    if k != a: vbal[k] += v
nodes = []
for a in used:
    key, kind, label = meta[a]
    b = bal.get(a, 0) if key == a else vbal.get(key, 0)
    nodes.append([a, KC[kind], label, ent_of.get(a, -1), round(max(b, 0) / 1e9, 4)])
edges = [[ix[s], ix[r], [[m, round(x[0] / 1e9, 4), round(x[1]), x[2]] for m, x in sorted(mm.items())]] for (s, r), mm in keep.items()]
months = [f"{day0.year + (day0.month - 1 + i) // 12}-{(day0.month - 1 + i) % 12 + 1:02d}" for i in range(month(T[-1][2]) + 1)]
out = dict(asOf=T[-1][2], spot=pa(T[-1][2]), months=months, kinds=list(KC), minUsd=MIN_USD,
           cols=dict(node=["key", "kind", "label", "entity", "balB"], edge=["from", "to", "[month, GME B, $, transfers]"]),
           entities=ents, nodes=nodes, edges=edges)
json.dump(out, open(os.path.join(D, "graph.json"), "w"), separators=(",", ":"))
print(f"graph.json: {len(nodes)} nodes ({sum(1 for n in nodes if n[1] == 0)} wallets, {sum(1 for n in nodes if n[1] == 2)} deposit addresses, "
      f"{sum(1 for n in nodes if n[1] in (3, 4))} venues/exchanges) · {len(edges)} links ≥ ${MIN_USD:.0f} (of {len(pairs)}) · {len(months)} months · "
      f"{os.path.getsize(os.path.join(D, 'graph.json')) / 1e6:.1f} MB")

# --- the ledger: the LEDGER_K largest transfers of every node ------------------------------------------------------
t0 = datetime.datetime.fromisoformat(T[0][2].replace("Z", "+00:00"))
top = collections.defaultdict(list)                               # node index -> heap of (usd, transfer index, from, to)
for p, k, v, u in legs:
    if p not in keep: continue
    i, j = ix[p[0]], ix[p[1]]
    for n in (i, j):
        h = top[n]
        if len(h) < LEDGER_K: heapq.heappush(h, (u, k, i, j))
        elif u > h[0][0]: heapq.heapreplace(h, (u, k, i, j))
pick = {}
for h in top.values():
    for u, k, i, j in h: pick[k] = (i, j, u)
rows = []
for k in sorted(pick):
    i, j, u = pick[k]
    mins = int((datetime.datetime.fromisoformat(T[k][2].replace("Z", "+00:00")) - t0).total_seconds() // 60)
    blk, li = KEYS[k] if KEYS else (T[k][4], -1)
    rows.append([mins, i, j, round(T[k][3] / 1e9, 4), round(u), blk, li])
led = dict(asOf=out["asOf"], t0=T[0][2], perNode=LEDGER_K, minUsd=1,
           cols=["minutesSinceLaunch", "from", "to", "GME B", "$", "block", "logIndex"], rows=rows)
json.dump(led, open(os.path.join(D, "graph_tx.json"), "w"), separators=(",", ":"))
cov = sum(r[4] for r in rows); allu = sum(u for _, _, _, u in legs)
print(f"graph_tx.json: {len(rows)} transfers (top {LEDGER_K} per node, {len(top)} nodes covered) · "
      f"${cov / 1e6:,.0f}M of ${allu / 1e6:,.0f}M ({100 * cov / allu:.0f}% of value) · "
      f"{os.path.getsize(os.path.join(D, 'graph_tx.json')) / 1e6:.1f} MB"
      + ("" if KEYS else " · WARNING: archive has no li column, logIndex is -1"))
