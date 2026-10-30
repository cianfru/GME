#!/usr/bin/env python3
# Pull GME(ETH)/USD daily prices from DeFiLlama (free, no key) and merge into prices.csv (day,price).
# Idempotent: re-pulls from a few days before the existing max date (to absorb corrections) to today,
# so it can run daily. Full history from 2023-04-28 on first run. Zero cost to any paid quota.
import os, ssl, json, sys, time, datetime, urllib.request

COIN = "ethereum:0xc56c7a0eaa804f854b536a5f3d5f49d2ec4b12b8"
OUT  = "prices.csv"
_CA  = os.environ.get("CURL_CA_BUNDLE") or "/root/.ccr/ca-bundle.crt"
_CTX = ssl.create_default_context(cafile=_CA) if os.path.exists(_CA) else ssl.create_default_context()
_PXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({"https": _PXY, "http": _PXY} if _PXY else {}),
    urllib.request.HTTPSHandler(context=_CTX),
)

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"})
    with _OPENER.open(req, timeout=40) as r:
        return json.load(r)

def load_existing(path):
    byday = {}
    if os.path.exists(path):
        with open(path) as f:
            next(f, None)
            for line in f:
                line = line.strip()
                if not line: continue
                d, p = line.split(",", 1)
                byday[d] = float(p)
    return byday

def main():
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
    out = args.get("out", OUT)
    byday = load_existing(out)
    if byday:
        last = max(byday)  # ISO date sorts lexicographically
        start = int(datetime.datetime.strptime(last, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp()) - 5 * 86400
    else:
        start = int(datetime.datetime(2024, 5, 13, tzinfo=datetime.timezone.utc).timestamp())
    now = int(time.time())
    s = start
    added = 0
    while s < now:
        url = f"https://coins.llama.fi/chart/{COIN}?start={s}&span=300&period=1d"
        try:
            d = get(url)
        except Exception as e:
            print("warn:", e, file=sys.stderr); time.sleep(2); continue
        pr = d.get("coins", {}).get(COIN, {}).get("prices", [])
        if not pr:
            s += 300 * 86400; continue
        for pt in pr:
            day = datetime.datetime.utcfromtimestamp(pt["timestamp"]).strftime("%Y-%m-%d")
            if day not in byday or byday[day] != pt["price"]:
                added += 1
            byday[day] = pt["price"]
        s = pr[-1]["timestamp"] + 86400
        time.sleep(0.3)
    rows = sorted(byday.items())
    with open(out, "w") as f:
        f.write("day,price\n")
        for d, p in rows:
            f.write(f"{d},{p}\n")
    print(f"wrote {len(rows)} daily prices ({rows[0][0]} → {rows[-1][0]}), {added} new/updated")

if __name__ == "__main__":
    main()
