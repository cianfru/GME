# Who signed each GME purchase into a study wallet, from free public nodes (eth_getTransactionByHash, batched).
# The signer paid the gas and the ETH; the GME went to the recipient. Signer ≠ recipient means one wallet bought for
# another: direct evidence the two are related, UNLESS the signer is a relayer or solver that signs for many
# unrelated wallets (CoW, 1inch Fusion, bots) — signers seen buying for more than 10 recipients are marked as relayers.
#   data/bq/signers.csv        tx,block,signer,recipient — only purchases whose signer is not the recipient
#   data/bq/signers_state.json last block checked, so later runs only look up new purchases (a signer never changes)
import sys, os, csv, json, time, importlib.util
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *
spec = importlib.util.spec_from_file_location("p", os.path.join(os.path.dirname(os.path.abspath(__file__)), "pull-transfers-rpc.py"))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
BQ = os.path.join(D, "bq"); os.makedirs(BQ, exist_ok=True)
OUT, ST = os.path.join(BQ, "signers.csv"), os.path.join(BQ, "signers_state.json")
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {V3POOL, "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
venue = lambda a: a in infra and a not in CEX and a not in LP and a not in (NULL, DEAD, TOKEN)
W = {r[0] for r in csv.reader(open(os.path.join(BQ, "wallets.csv"))) if r and r[0] != "a"}
state = json.load(open(ST)) if os.path.exists(ST) else {"lastBlock": 0}
todo = {}                                                        # tx → (block, recipients)
with open(os.path.join(D, "transfers.csv")) as f:
    h = next(f).strip().split(",")
    if "tx" not in h: sys.exit("archive has no tx column")
    ti = h.index("tx")
    for r in csv.reader(f):
        b = int(r[4])
        if b > state["lastBlock"] and venue(r[0]) and r[1] in W:
            todo.setdefault(r[ti], [b, set()])[1].add(r[1])
txs = sorted(todo, key=lambda t: todo[t][0])
print(f"{len(txs)} purchases to look up (after block {state['lastBlock']})", flush=True)

def batch(hashes):
    body = json.dumps([{"jsonrpc": "2.0", "id": i, "method": "eth_getTransactionByHash", "params": [x]} for i, x in enumerate(hashes)]).encode()
    for t in range(8):
        url = p.RPCS[t % len(p.RPCS)]
        try:
            req = p.urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": p._UA})
            with p._OPENER.open(req, timeout=60) as resp: d = json.load(resp)
            if isinstance(d, list):
                got = {x["id"]: (x.get("result") or {}).get("from") for x in d if isinstance(x, dict)}
                if all(got.get(i) for i in range(len(hashes))): return [got[i].lower() for i in range(len(hashes))]
            time.sleep(0.5 + 0.5 * t)
        except Exception as e:
            time.sleep(0.8 + 0.6 * t)
    return None

new = open(OUT, "a"); 
if os.path.getsize(OUT) == 0: new.write("tx,block,signer,recipient\n")
size, i, done, mism, maxb = 25, 0, 0, 0, state["lastBlock"]
while i < len(txs):
    chunk = txs[i:i + size]; res = batch(chunk)
    if res is None:
        if size > 1: size = max(1, size // 2); continue
        print(f"gave up at {chunk[0]}; the next run resumes here"); break
    for tx, sg in zip(chunk, res):
        b, rec = todo[tx]
        for r in rec:
            if sg != r: new.write(f"{tx},{b},{sg},{r}\n"); mism += 1
        maxb = max(maxb, b)
    i += len(chunk); done += len(chunk); size = min(50, size + 5)
    if done % 2000 < len(chunk):
        new.flush(); json.dump({"lastBlock": maxb - 1}, open(ST, "w")); print(f"  {done}/{len(txs)} looked up · {mism} bought for another wallet", flush=True)
    time.sleep(0.15)
new.close()
if i >= len(txs): json.dump({"lastBlock": maxb}, open(ST, "w"))
else: json.dump({"lastBlock": min(todo[t][0] for t in txs[i:]) - 1}, open(ST, "w"))
print(f"signers: {done} purchases looked up, {mism} new purchases signed by another wallet")
