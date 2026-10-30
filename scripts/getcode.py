# Classify every address in transfers.csv: eoa / 7702 (delegated EOA = a person) / contract, via batched eth_getCode.
import csv, json, os, sys, time, importlib.util
spec = importlib.util.spec_from_file_location("p", os.path.join(os.path.dirname(__file__), "pull-transfers-rpc.py"))
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
import urllib.request
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT = os.path.join(D, "addr-types.json")
types = json.load(open(OUT)) if os.path.exists(OUT) else {}
addrs = set()
for r in csv.reader(open(os.path.join(D, "transfers.csv"))):
    if r[0] == "sender": continue
    addrs.add(r[0]); addrs.add(r[1])
todo = sorted(a for a in addrs if a not in types)
print(len(addrs), "addresses,", len(todo), "to classify", flush=True)
def batch(chunk, url):
    body = json.dumps([{"jsonrpc": "2.0", "id": i, "method": "eth_getCode", "params": [a, "latest"]} for i, a in enumerate(chunk)]).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "curl/8.5.0"})
    with p._OPENER.open(req, timeout=60) as r: return json.load(r)
B = 50; i = 0; k = 0
while i < len(todo):
    chunk = todo[i:i + B]
    try:
        res = batch(chunk, p.RPCS[k % 2])
        got = {x["id"]: x.get("result") for x in res if isinstance(x, dict)}
        if len(got) < len(chunk) or any(v is None for v in got.values()): raise RuntimeError("partial")
        for j, a in enumerate(chunk):
            c = got[j] or "0x"
            types[a] = "eoa" if c in ("0x", "0x0") else ("7702" if c.startswith("0xef0100") else "contract")
        i += B
        if (i // B) % 40 == 0:
            json.dump(types, open(OUT, "w")); print(i, "done", flush=True)
        time.sleep(0.05)
    except Exception as e:
        k += 1; time.sleep(1.0)
json.dump(types, open(OUT, "w"))
from collections import Counter
print(Counter(types.values()))
