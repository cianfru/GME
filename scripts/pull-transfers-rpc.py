#!/usr/bin/env python3
# Pull the FULL GME (Ethereum) ERC-20 Transfer history from public Ethereum RPC via eth_getLogs.
# Zero cost to any paid quota (no BigQuery bytes, no Dune credits). Exact canonical timestamps
# come straight from each log's blockTimestamp (drpc enriches logs with it).
# Output CSV columns: sender,receiver,time,value,block,tx,li — engine format (it reads sender/receiver/
# time/value by name and ignores the rest; `block` lets the incremental refresh merge on a clean block
# boundary; tx = transaction hash, li = log index, so a transfer can be tied to the swap in the same
# transaction). value = raw uint256 decimal.
# The same eth_getLogs call also returns the Swap events of the GME pools (Uniswap V2 pair, V3 pool), written to
# --swaps (pool,time,block,li,tx,wethIn,wethOut,gmeIn,gmeOut; raw integers, WETH is token0 in both pools):
# the exact ETH paid or received in every trade.
#
# Usage:
#   full pull:  python scripts/pull-transfers-rpc.py                       (finds the deploy block)
#   delta pull: python scripts/pull-transfers-rpc.py --start-block=N --out=delta.csv
#   options:    --out=PATH  --swaps=PATH  --log=PATH  --start-block=N
import json, sys, time, os, ssl, urllib.request, urllib.error

# Portable across environments: in the agent sandbox the proxy allowlists by User-Agent (curl OK,
# python-urllib blocked) and needs its CA bundle; on a bare CI runner there's no proxy and the system
# CA is used. Fall back gracefully so the same script runs in both.
_CA  = os.environ.get("CURL_CA_BUNDLE") or "/root/.ccr/ca-bundle.crt"
_CTX = ssl.create_default_context(cafile=_CA) if os.path.exists(_CA) else ssl.create_default_context()
_PXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({"https": _PXY, "http": _PXY} if _PXY else {}),
    urllib.request.HTTPSHandler(context=_CTX),
)
_UA = "curl/8.5.0"

CA    = "0xc56c7a0eaa804f854b536a5f3d5f49d2ec4b12b8"
TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"  # Transfer(address,address,uint256)
PAIR  = "0x2aeee741fa1e21120a21e57db9ee545428e683c9"   # Uniswap V2 WETH/GME
V3P   = "0x05391bd57d8c6fb30d9c39f6618f2207893922dc"   # Uniswap V3 WETH/GME (1%)
SWAP2 = "0xd78ad95fa46c994b6551d0da85fc275fe613ce37657fb8d5e3d130840159d822"  # Swap(address,uint,uint,uint,uint,address)
SWAP3 = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"  # Swap(address,address,int,int,uint160,uint128,int24)
RPCS  = ["https://eth.drpc.org", "https://rpc.mevblocker.io"]  # both enrich logs w/ blockTimestamp + survive bursts
OUT   = "transfers.csv"
SWAPS = None
TH    = "sender,receiver,time,value,block,tx,li\n"
SH    = "pool,time,block,li,tx,wethIn,wethOut,gmeIn,gmeOut\n"
def s256(h): v = int(h, 16); return v - (1 << 256) if v >= 1 << 255 else v
LOG   = "pull.log"

def log(m):
    with open(LOG, "a") as f: f.write(f"{time.strftime('%H:%M:%S')} {m}\n")

def rpc(method, params, tries=8):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    last = None
    for t in range(tries):
        url = RPCS[t % len(RPCS)]   # drpc first (enriches logs w/ blockTimestamp), publicnode failover
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type":"application/json","User-Agent":_UA})
            with _OPENER.open(req, timeout=40) as r:
                d = json.load(r)
            if "error" in d and d["error"] is not None:
                last = d["error"]
                msg = str(last).lower()
                # result-too-large / range-too-wide → signal caller to shrink
                if any(k in msg for k in ("more than","larger than","exceed","too large","range","limit","10000","result set")):
                    return {"_shrink": True, "err": last}
                time.sleep(0.4); continue
            return {"result": d.get("result")}
        except urllib.error.HTTPError as e:
            # 403/429 from the proxy or node under a large/burst response → shrink the range (self-corrects via regrow)
            if e.code in (403, 429, 413):
                return {"_shrink": True, "err": f"HTTP {e.code}"}
            last = f"HTTP {e.code}"; time.sleep(0.5 + 0.3*t); continue
        except Exception as e:
            last = str(e); time.sleep(0.6 + 0.3*t); continue
    return {"_fail": True, "err": last}

def get_latest():
    for _ in range(5):
        r = rpc("eth_blockNumber", [])
        if r.get("result"): return int(r["result"], 16)
        time.sleep(1)
    raise SystemExit("could not get latest block")

def deployed_at(mid):
    # O(1) per call (no scan): code present ⇒ contract deployed at/before this block. Monotonic.
    r = rpc("eth_getCode", [CA, hex(mid)])
    if r.get("_fail"): return None
    code = r.get("result") or "0x"
    return code not in ("0x", "0x0", "")

def find_creation(latest):
    lo, hi = 0, latest
    while lo < hi:
        mid = (lo + hi)//2
        ex = deployed_at(mid)
        if ex is None: time.sleep(1); continue
        if ex: hi = mid
        else:  lo = mid + 1
    return lo

def norm_addr(topic):  # 32-byte padded → 0x + last 40 hex
    return "0x" + topic[-40:]

def main():
    global OUT, LOG, SWAPS
    args = dict(a[2:].split("=", 1) if "=" in a else (a[2:], True) for a in sys.argv[1:] if a.startswith("--"))
    OUT = args.get("out", OUT)
    SWAPS = args.get("swaps", os.path.join(os.path.dirname(OUT) or ".", "swaps.csv" if os.path.basename(OUT) == "transfers.csv" else "delta_swaps.csv"))
    LOG = args.get("log", LOG)
    open(LOG, "w").close()
    latest = get_latest()
    log(f"latest block {latest}")
    if "start-block" in args:
        start = int(args["start-block"])
        log(f"delta pull from block {start} → {latest} ({latest-start} blocks)")
    else:
        start = find_creation(latest)
        log(f"creation/first-log block ~{start}  (span {latest-start} blocks)")
    if start > latest:
        f = open(OUT, "w"); f.write(TH); f.close(); open(SWAPS, "w").write(SH)
        log("DONE: 0 transfers (archive already at tip)"); print("DONE 0 transfers"); return

    f = open(OUT, "w"); f.write(TH); fs = open(SWAPS, "w"); fs.write(SH)
    span = 2000; frm = start; n = 0; ns = 0; calls = 0
    while frm <= latest:
        to = min(frm + span, latest)
        r = rpc("eth_getLogs", [{"address":[CA, PAIR, V3P],"topics":[[TOPIC, SWAP2, SWAP3]],"fromBlock":hex(frm),"toBlock":hex(to)}])
        calls += 1
        if r.get("_shrink"):
            span = max(1, span//2); log(f"shrink→{span} at {frm}"); continue
        if r.get("_fail"):
            log(f"FAIL at {frm}: {r.get('err')}; retry smaller"); span = max(1, span//2); time.sleep(1); continue
        res = r["result"]
        if len(res) >= 8000 and span > 1:   # possible silent cap → rescan this range smaller (loop-safe: only when span>1)
            span = max(1, span//2); log(f"dense {len(res)}→shrink {span} rescan {frm}"); continue
        for lg in res:
            ts = lg.get("blockTimestamp")
            if ts is None:
                # fallback: resolve via block header (rare; cache per block)
                bn = lg["blockNumber"]
                ts = block_ts(bn)
            sec = int(ts, 16) if isinstance(ts, str) else int(ts)
            bn  = int(lg["blockNumber"], 16); li = int(lg["logIndex"], 16); txh = lg["transactionHash"].lower()
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sec))
            addr = lg["address"].lower(); t0 = lg["topics"][0].lower(); d = lg["data"][2:]
            if addr == CA and t0 == TOPIC:
                frm_a = norm_addr(lg["topics"][1]); to_a = norm_addr(lg["topics"][2])
                val = int(lg["data"], 16)          # exact big-int
                f.write(f"{frm_a},{to_a},{iso},{val},{bn},{txh},{li}\n"); n += 1
            elif addr == PAIR and t0 == SWAP2:     # amount0In, amount1In, amount0Out, amount1Out (token0 = WETH)
                a0i, a1i, a0o, a1o = (int(d[i:i + 64], 16) for i in range(0, 256, 64))
                fs.write(f"v2,{iso},{bn},{li},{txh},{a0i},{a0o},{a1i},{a1o}\n"); ns += 1
            elif addr == V3P and t0 == SWAP3:      # amount0, amount1: signed, positive = into the pool
                a0, a1 = s256(d[0:64]), s256(d[64:128])
                fs.write(f"v3,{iso},{bn},{li},{txh},{max(a0, 0)},{max(-a0, 0)},{max(a1, 0)},{max(-a1, 0)}\n"); ns += 1
        if len(res) < 2000: span = min(100000, max(span, 1)*2)   # grow when sparse
        frm = to + 1
        time.sleep(0.1)   # gentle pacing to avoid proxy rate-limit
        if calls % 25 == 0:
            f.flush(); fs.flush(); log(f"{calls} calls · block {frm}/{latest} · {n} transfers · {ns} swaps · span {span}")
    f.close(); fs.close()
    log(f"DONE: {n} transfers, {ns} swaps, {calls} calls → {OUT}, {SWAPS}")
    print(f"DONE {n} transfers, {ns} swaps")

_bts = {}
def block_ts(bn):
    if bn in _bts: return _bts[bn]
    r = rpc("eth_getBlockByNumber", [bn, False])
    ts = r["result"]["timestamp"]; _bts[bn] = ts; return ts

if __name__ == "__main__":
    main()
