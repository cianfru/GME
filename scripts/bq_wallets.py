# The study wallets uploaded to BigQuery (data/bq/wallets.csv) and the DEX purchases whose signer we look up
# (data/bq/txs.csv). Study wallets = every entity member and provisional wallet, every wallet that ever held
# ≥0.05% of supply, every wallet holding ≥0.01% now, and every buyer of ≥$500 in the last 180 days.
import sys, os, csv, json, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
T = load(); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {V3POOL, "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
venue = lambda a: a in infra and a not in CEX and a not in LP and a not in (NULL, DEAD, TOKEN)
NOW = T[-1][2]; c180 = (datetime.date.fromisoformat(NOW[:10]) - datetime.timedelta(days=180)).isoformat()
role = collections.defaultdict(set)
REG = json.load(open(os.path.join(D, "entities.json"))) if os.path.exists(os.path.join(D, "entities.json")) else {"entities": []}
for e in REG["entities"]:
    for a in e["members"]: role[a].add("entity")
    for p in e.get("provisional", []): role[p["a"]].add("provisional")
bal = collections.Counter(); peak = collections.Counter(); buy = collections.Counter()
for s, r, ts, v, b in T:
    bal[s] -= v; bal[r] += v
    if bal[r] > peak[r]: peak[r] = bal[r]
    if ts[:10] >= c180 and venue(s) and r not in infra: buy[r] += v * pa(ts)
for a, p in peak.items():
    if a in infra: continue
    if p >= 0.0005 * SUPPLY: role[a].add("peak")
    if bal[a] >= 0.0001 * SUPPLY: role[a].add("holder")
    if buy[a] >= 500: role[a].add("buyer")
os.makedirs(os.path.join(D, "bq"), exist_ok=True)
with open(os.path.join(D, "bq", "wallets.csv"), "w") as f:
    f.write("a,role\n")
    for a, rs in sorted(role.items()):
        if a not in infra: f.write(f"{a},{'|'.join(sorted(rs))}\n")
keys = None
with open(os.path.join(D, "transfers.csv")) as f:
    h = next(f).strip().split(",")
    if "tx" in h:
        ti = h.index("tx"); n = 0
        with open(os.path.join(D, "bq", "txs.csv"), "w") as o:
            o.write("tx\n"); seen = set()
            for r in csv.reader(f):
                if venue(r[0]) and r[1] not in infra and r[ti] not in seen: seen.add(r[ti]); o.write(r[ti] + "\n"); n += 1
        print(f"txs.csv: {n} DEX purchase transactions")
    else: print("archive has no tx column: no txs.csv")
print(f"wallets.csv: {sum(1 for a in role if a not in infra)} study wallets · " + " · ".join(f"{k} {sum(1 for rs in role.values() if k in rs)}" for k in ("entity", "provisional", "peak", "holder", "buyer")))
