# Daily ETH/USD from DeFiLlama (free, no key) → data/eth_prices.csv (day,price). Idempotent.
import os, sys, ssl, json, time, datetime, urllib.request
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "eth_prices.csv")
_CA = "/root/.ccr/ca-bundle.crt"
ctx = ssl.create_default_context(cafile=_CA) if os.path.exists(_CA) else ssl.create_default_context()
px = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
op = urllib.request.build_opener(urllib.request.ProxyHandler({"https": px} if px else {}), urllib.request.HTTPSHandler(context=ctx))
C = "coingecko:ethereum"
have = {}
if os.path.exists(OUT):
    for line in open(OUT).read().splitlines()[1:]:
        d, p = line.split(","); have[d] = float(p)
start = datetime.datetime(2024, 5, 1, tzinfo=datetime.timezone.utc)
if have: start = datetime.datetime.fromisoformat(max(have)).replace(tzinfo=datetime.timezone.utc) - datetime.timedelta(days=5)
s = int(start.timestamp())
while s < time.time():
    d = json.load(op.open(urllib.request.Request(f"https://coins.llama.fi/chart/{C}?start={s}&span=300&period=1d", headers={"User-Agent": "curl/8.5.0"}), timeout=40))
    pr = d["coins"].get(C, {}).get("prices", [])
    if not pr: break
    for x in pr: have[datetime.datetime.fromtimestamp(x["timestamp"], datetime.timezone.utc).strftime("%Y-%m-%d")] = x["price"]
    s = pr[-1]["timestamp"] + 86400
open(OUT, "w").write("day,price\n" + "".join(f"{k},{v}\n" for k, v in sorted(have.items())))
print(f"wrote {len(have)} ETH prices → {OUT}")
