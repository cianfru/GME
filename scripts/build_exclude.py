# Build data/exclude.json — the GME infrastructure list (pools, routers, contracts, exchanges) removed from the
# holder reconstruction. Contracts come from eth_getCode (EIP-7702 delegated EOAs are PEOPLE and stay in).
import json, csv, os
D = os.path.join(os.path.dirname(__file__), "..", "data")
types = json.load(open(f"{D}/addr-types.json"))
names = {}
for f in ["infra_candidates.json", "holding_contracts.json"]:
    p = f"{D}/bs/{f}"
    if os.path.exists(p):
        for a, v in json.load(open(p)).items(): names[a] = v.get("name") if isinstance(v, dict) else v
cexlab = {a: n for a, n in csv.reader(open(f"{D}/eth_labels.csv"))}
ex = {
 "0x0000000000000000000000000000000000000000": {"name": "null / mint source", "kind": "null"},
 "0x000000000000000000000000000000000000dead": {"name": "burn", "kind": "burn"},
 "0x2aeee741fa1e21120a21e57db9ee545428e683c9": {"name": "Uniswap V2: GME/WETH (LP burned)", "kind": "lp"},
 "0x05391bd57d8c6fb30d9c39f6618f2207893922dc": {"name": "Uniswap V3: GME/WETH", "kind": "lp"},
 "0xc56c7a0eaa804f854b536a5f3d5f49d2ec4b12b8": {"name": "GME token contract (launch-tax float)", "kind": "mm"},
 "0x9642b23ed1e01df1092b92641051881a322f5d4e": {"name": "MEXC 2", "kind": "cex"},
 "0x3cc936b795a188f0e246cbb2d74c5bd190aecf18": {"name": "MEXC sweeper", "kind": "cex"},
 "0x0d0707963952f2fba59dd06f2b425ace40b492fe": {"name": "Gate.io 1", "kind": "cex"},
 "0x8fca4ade3a517133ff23ca55cdaea29c78c990b8": {"name": "Unidentified exchange hot wallet", "kind": "cex"},
 "0xf81b45b1663b7ea8716c74796d99bbe4ea26f488": {"name": "Unidentified exchange/OTC hot wallet", "kind": "cex"},
}
for a, n in cexlab.items():
    if a in types and a not in ex: ex[a] = {"name": n, "kind": "cex"}
for a, t in types.items():
    if t != "contract" or a in ex: continue
    n = names.get(a) or "contract"
    kind = "lp" if any(k in n for k in ("Pool", "Pair", "LP Token", "PoolManager")) else "mm"
    ex[a] = {"name": n, "kind": kind}
json.dump(ex, open(f"{D}/exclude.json", "w"), indent=0)
from collections import Counter
print(len(ex), Counter(v["kind"] for v in ex.values()))
