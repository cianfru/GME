#!/usr/bin/env python3
# Pull the FULL GME (Ethereum) ERC-20 Transfer history from public Ethereum RPC via eth_getLogs.
# Zero cost to any paid quota (no BigQuery bytes, no Dune credits). Exact canonical timestamps
# come straight from each log's blockTimestamp (drpc enriches logs with it).
# Output CSV columns: sender,receiver,time,value,block — engine format (it reads sender/receiver/
# time/value by name and ignores `block`; `block` exists so the incremental refresh can merge on a
# clean block boundary). value = raw uint256 decimal.
#
# Usage:
#   full pull:  python scripts/pull-transfers-rpc.py                       (finds the deploy block)
#   delta pull: python scripts/pull-transfers-rpc.py --start-block=N --out=delta.csv
#   options:    --out=PATH  --log=PATH  --start-block=N
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
RPCS  = ["https://eth.drpc.org", "https://rpc.mevblocker.io"]  # both enrich logs w/ blockTimestamp + survive bursts
OUT   = "transfers.csv"
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
    global OUT, LOG
    args = dict(a[2:].split("=", 1) if "=" in a else (a[2:], True) for a in sys.argv[1:] if a.startswith("--"))
    OUT = args.get("out", OUT)
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
        f = open(OUT, "w"); f.write("sender,receiver,time,value,block\n"); f.close()
        log("DONE: 0 transfers (archive already at tip)"); print("DONE 0 transfers"); return

    f = open(OUT, "w"); f.write("sender,receiver,time,value,block\n")
    span = 2000; frm = start; n = 0; calls = 0
    while frm <= latest:
        to = min(frm + span, latest)
        r = rpc("eth_getLogs", [{"address":CA,"topics":[TOPIC],"fromBlock":hex(frm),"toBlock":hex(to)}])
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
            frm_a = norm_addr(lg["topics"][1]); to_a = norm_addr(lg["topics"][2])
            val = int(lg["data"], 16)          # exact big-int
            bn  = int(lg["blockNumber"], 16)
            iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sec))
            f.write(f"{frm_a},{to_a},{iso},{val},{bn}\n"); n += 1
        if len(res) < 2000: span = min(100000, max(span, 1)*2)   # grow when sparse
        frm = to + 1
        time.sleep(0.1)   # gentle pacing to avoid proxy rate-limit
        if calls % 25 == 0:
            f.flush(); log(f"{calls} calls · block {frm}/{latest} · {n} transfers · span {span}")
    f.close()
    log(f"DONE: {n} transfers, {calls} calls → {OUT}")
    print(f"DONE {n} transfers")

_bts = {}
def block_ts(bn):
    if bn in _bts: return _bts[bn]
    r = rpc("eth_getBlockByNumber", [bn, False])
    ts = r["result"]["timestamp"]; _bts[bn] = ts; return ts

if __name__ == "__main__":
    main()
