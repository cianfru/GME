# The Visualizer's data: every GME transfer since launch, aggregated per directed pair and per calendar month.
#   data/graph.json — fetched only by the Visualizer page (#visualizer).
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
import sys, json, os, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *

MIN_USD = 25.0
T = load(); pa = prices(); PX = exact_prices(T, pa)
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
AT = json.load(open(os.path.join(D, "addr-types.json"))) if os.path.exists(os.path.join(D, "addr-types.json")) else {}
LPS = {"0xc36442b4a4522e871399cd717abdd847ab11fe88"}                # Uniswap V3 positions (liquidity, not trades)
REG = json.load(open(os.path.join(D, "entities.json"))) if os.path.exists(os.path.join(D, "entities.json")) else {"entities": []}

outs = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: outs[s][r] += v
def pays_into(a):
    o = outs.get(a)
    if not o or a in infra: return None
    tot = sum(o.values()); cx = {k: x for k, x in o.items() if k in CEX}
    if tot > 0 and sum(cx.values()) / tot >= 0.95: return max(cx, key=cx.get)
    return None
deposit = {a: x for a in outs if (x := pays_into(a))}

ROUTERS = {"0x66a9893cc07d91d95644aedd05d03f95e1dba8af": "Uniswap app", "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap app",
           "0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b": "Uniswap app", "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 router",
           "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 router", "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 router",
           "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch", "0x111111125421ca6dc452d289314280a0f8842a65": "1inch",
           "0x9008d19f58aabd9ed0d60971565aa8510560ab41": "CoW Protocol", "0x000000000004444c5dc75cb358380d2e3de08a90": "Uniswap v4"}
NAMES = {"MainnetSettler": "0x / Matcha", "ZeroExProxy": "0x / Matcha", "TransitSwapRouterV5": "TransitSwap", "DexRouter": "OKX DEX", "RainbowRouter": "Rainbow wallet"}
def node_of(a):
    """(key, kind, label): the node an address is drawn as."""
    if a == NULL: return "v:mint", "mint", "Mint"
    if a == DEAD: return "v:burn", "burn", "Burn address"
    if a == TOKEN: return "v:token", "token", "GME token contract"
    if a == PAIR: return "v:pair", "dex", "Uniswap V2 · GME/WETH"
    if a == V3POOL: return "v:v3", "dex", "Uniswap V3 · GME/WETH"
    if a in LPS: return "v:lp", "lp", "Uniswap V3 positions"
    if a in CEX: n = EX[a].get("name") or "Exchange"; return "x:" + a, "cex", n
    if a in ROUTERS: n = ROUTERS[a]; return "v:" + n, "dex", n
    if a in infra:
        n = EX[a].get("name", "")
        if n in NAMES: return "v:" + NAMES[n], "dex", NAMES[n]
        return "v:routers", "dex", "Other routers & bots"
    if a in deposit: return a, "deposit", (EX.get(deposit[a], {}).get("name") or "Exchange") + " deposit"
    return a, "contract" if AT.get(a) == "contract" else "wallet", ""

day0 = datetime.date.fromisoformat(T[0][2][:10])
month = lambda ts: (int(ts[:4]) - day0.year) * 12 + int(ts[5:7]) - day0.month
pairs = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0, 0]))
meta = {}
bal = collections.Counter()
for k, (s, r, ts, v, b) in enumerate(T):
    bal[s] -= v; bal[r] += v
    if s == r: continue
    ns, nr = node_of(s), node_of(r)
    if ns[0] == nr[0]: continue
    meta.setdefault(ns[0], ns); meta.setdefault(nr[0], nr)
    x = pairs[(ns[0], nr[0])][month(ts)]; x[0] += v; x[1] += v * PX[k]; x[2] += 1
keep = {p: m for p, m in pairs.items() if sum(x[1] for x in m.values()) >= MIN_USD}

ent_of, ents = {}, []
for i, e in enumerate(REG.get("entities", [])):
    ents.append([e["id"], e["name"], e.get("tag", ""), e["kind"], round(e["bal"] / 1e9, 4), e["n"]])
    for a in e["members"]: ent_of[a] = i
used = sorted({a for p in keep for a in p}, key=lambda a: (meta[a][1] == "wallet", -bal.get(a, 0)))
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
