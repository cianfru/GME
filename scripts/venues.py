# Names for the infrastructure a GME transfer can touch, shared by graph.py (the Visualizer) and wallet_index.py (the
# Wallet page), so a counterparty is labelled the same way everywhere.
#   - DEX: the Uniswap pools, Uniswap's routers, 1inch, 0x, CoW and other aggregators by name; unnamed routers and
#     bots are "Other routers & bots";
#   - exchanges: each labelled exchange wallet (exclude.json kind cex) by its name;
#   - exchange deposit addresses: an address that forwarded ≥95% of the GME it ever sent to labelled exchange wallets,
#     named after the exchange it pays into;
#   - burn, mint, the token contract and the V3 positions (liquidity) by name.
import collections
from txlib import PAIR, V3POOL, TOKEN, NULL, DEAD

LPS = {"0xc36442b4a4522e871399cd717abdd847ab11fe88"}                # Uniswap V3 positions (liquidity, not trades)
ROUTERS = {"0x66a9893cc07d91d95644aedd05d03f95e1dba8af": "Uniswap app", "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap app",
           "0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b": "Uniswap app", "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 router",
           "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 router", "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "Uniswap V3 router",
           "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch", "0x111111125421ca6dc452d289314280a0f8842a65": "1inch",
           "0x9008d19f58aabd9ed0d60971565aa8510560ab41": "CoW Protocol", "0x000000000004444c5dc75cb358380d2e3de08a90": "Uniswap v4"}
NAMES = {"MainnetSettler": "0x / Matcha", "ZeroExProxy": "0x / Matcha", "TransitSwapRouterV5": "TransitSwap", "DexRouter": "OKX DEX", "RainbowRouter": "Rainbow wallet"}


def deposits(T, EX):
    """{deposit address: the exchange wallet it pays into} for every non-infrastructure address that sent ≥95% of its
    GME to labelled exchange wallets. T rows are (sender, receiver, ts, GME, block)."""
    CEX = {a for a, v in EX.items() if v["kind"] == "cex"}
    outs = collections.defaultdict(lambda: collections.defaultdict(float))
    for s, r, ts, v, b in T: outs[s][r] += v
    dep = {}
    for a, o in outs.items():
        if a in EX: continue
        tot = sum(o.values()); cx = {k: x for k, x in o.items() if k in CEX}
        if tot > 0 and sum(cx.values()) / tot >= 0.95: dep[a] = max(cx, key=cx.get)
    return dep


def node(a, EX, dep, AT=None):
    """(key, kind, label): how an address is drawn and named. kind is one of wallet, contract, deposit, cex, dex, lp,
    burn, mint, token. Venues collapse to one key (all Uniswap app routers are one node); wallets keep their address."""
    if a == NULL: return "v:mint", "mint", "Mint"
    if a == DEAD: return "v:burn", "burn", "Burn address"
    if a == TOKEN: return "v:token", "token", "GME token contract"
    if a == PAIR: return "v:pair", "dex", "Uniswap V2 · GME/WETH"
    if a == V3POOL: return "v:v3", "dex", "Uniswap V3 · GME/WETH"
    if a in LPS: return "v:lp", "lp", "Uniswap V3 positions"
    x = EX.get(a)
    if x and x["kind"] == "cex": return "x:" + a, "cex", x.get("name") or "Exchange"
    if a in ROUTERS: return "v:" + ROUTERS[a], "dex", ROUTERS[a]
    if x:
        n = x.get("name", "")
        if n in NAMES: return "v:" + NAMES[n], "dex", NAMES[n]
        return "v:routers", "dex", "Other routers & bots"
    if a in dep: return a, "deposit", ((EX.get(dep[a]) or {}).get("name") or "Exchange") + " deposit"
    return a, "contract" if (AT or {}).get(a) == "contract" else "wallet", ""
