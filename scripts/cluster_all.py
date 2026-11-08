# Link wallets across ALL GME holders with the same conservative rules used for the focus cluster:
#   seed  — B had never held GME and A gave it its first GME (≥ MIN_USD at the day's price)
#   drain — A sent ≥90% of its balance to B in one transfer (≥ MIN_USD)
#   deposit — both sent GME to the same exchange deposit address (2–10 depositors)
#   ethseed / gas / paid — the strong ETH links of the last ethside.py run (data/eth_links.json): A sent B its first
#             ETH, A topped B up with ≤0.05 ETH, or A signed a swap that delivered GME from a pool straight to B.
#             ethside.py already drops exchanges, services, relayers and OTC-like pairs.
# Guards: a wallet that seeds >40 wallets is a distributor (no linking through it); nothing links through
# infrastructure, exchange deposit addresses or contracts; groups >60 wallets are flagged.
# Each group lists how many links of each kind hold it together ("via").
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
groups = collections.defaultdict(set); via = collections.defaultdict(collections.Counter)
for a in parent: groups[find(a)].add(a)
for s, r, k, d in kept: via[find(s)][k] += 1
FOC = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
CBG = {r["a"] for r in json.load(open(os.path.join(D, "coinbase_group.json")))} | {"0xe1fc21df6bbe9caa933f93896866501375669717"}
ents = []
for root, g in groups.items():
    if len(g) < 2: continue
    held = sum(max(bal[a], 0) for a in g)
    ents.append(dict(wallets=sorted(g), n=len(g), held=held, focus=len(g & FOC), cb=len(g & CBG), flagged=len(g) > 60, via=dict(via[root])))
ents.sort(key=lambda e: -e["held"])
json.dump(dict(hubs=sorted(hubs), entities=ents), open(os.path.join(D, "entities_all.json"), "w"))
print(f"{len(ents)} multi-wallet groups · {sum(e['n'] for e in ents)} wallets · hubs dropped {len(hubs)} · {n_eth} strong ETH links used · "
      f"{sum(1 for e in ents if any(k in e['via'] for k in ('ethseed', 'gas', 'paid')))} groups hold one")
for e in ents[:25]:
    top = max(e["wallets"], key=lambda a: bal[a])
    print(f"{e['n']:4d} wallets  {e['held']/1e9:6.2f}B ({100*e['held']/SUPPLY:4.2f}%)  focus-overlap {e['focus']:3d}  coinbase-overlap {e['cb']:2d}  {'FLAGGED' if e['flagged'] else ''}  largest {top} {bal[top]/1e9:.2f}B")
