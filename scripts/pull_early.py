# Targeted pull of the launch window WITH tx hashes: GME Transfer logs + Uniswap V2 pair Swap logs,
# so early buys can be priced exactly in ETH (the daily DeFiLlama close starts 3 days after launch).
import json, sys, os, time, importlib.util
spec = importlib.util.spec_from_file_location("p", os.path.join(os.path.dirname(__file__), "pull-transfers-rpc.py"))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
GME = "0xc56c7a0eaa804f854b536a5f3d5f49d2ec4b12b8"
PAIR = "0x2aeee741fa1e21120a21e57db9ee545428e683c9"
SWAP = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
lo, hi = int(sys.argv[1]), int(sys.argv[2]); out = sys.argv[3]
p.LOG = out + ".log"
def pull(addr, topic):
    res, frm, span = [], lo, 500
    while frm <= hi:
        to = min(frm + span, hi)
        r = p.rpc("eth_getLogs", [{"address": addr, "topics": [topic], "fromBlock": hex(frm), "toBlock": hex(to)}])
        if r.get("_shrink") or r.get("_fail"): span = max(1, span // 2); time.sleep(0.5); continue
        res += r["result"]; frm = to + 1; time.sleep(0.1)
    return res
t = pull(GME, TRANSFER); s = pull(PAIR, SWAP)
json.dump({"transfers": t, "swaps": s}, open(out, "w"))
print(len(t), "transfers", len(s), "swaps")
