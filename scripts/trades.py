# Exact execution prices for DEX trades, from the GME pools' own Swap events (data/swaps.csv, pulled with the
# transfers by pull-transfers-rpc.py).
# For every transaction that swapped GME in the Uniswap V2 pair or the V3 pool, both pools summed:
#   buy price  = WETH paid into the pools ÷ GME paid out
#   sell price = WETH paid out ÷ GME paid in
# Each GME transfer in that transaction between a pool/router and a wallet gets that price: pool/router → wallet is a
# buy, wallet → pool/router a sale. USD = WETH × that day's ETH close (ETH moves far less in a day than GME does).
# Trades with no GME swap in the transaction (peer-to-peer settlements, other venues) keep the day's GME close.
#   data/trade_px.csv     block,li,usd,weth,side — rebuilt every run from the archive, not committed
#   data/trades_check.json how far the day's close was from the real price, by volume and per month
import sys, os, csv, json, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *

EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {V3POOL, "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
venue = lambda a: a in infra and a not in CEX and a not in LP and a not in (NULL, DEAD, TOKEN)   # pool, router, aggregator
pa, pe = prices(), prices("eth_prices.csv")
SP = os.path.join(D, "swaps.csv")
if not os.path.exists(SP): print("no swaps.csv: nothing to price"); sys.exit(0)
sw = collections.defaultdict(lambda: [0, 0, 0, 0])            # tx → buy WETH in, buy GME out, sell WETH out, sell GME in
with open(SP) as f:
    next(f)
    for r in csv.reader(f):
        wi, wo, gi, go = int(r[5]), int(r[6]), int(r[7]), int(r[8]); x = sw[r[4]]
        if go > 0 and wi > 0: x[0] += wi; x[1] += go
        if gi > 0 and wo > 0: x[2] += wo; x[3] += gi
with open(os.path.join(D, "transfers.csv")) as f:
    h = next(f).strip().split(",")
    if "tx" not in h: print("archive has no tx column yet: nothing to price"); sys.exit(0)
    ti, li_ = h.index("tx"), h.index("li")
    out = open(os.path.join(D, "trade_px.csv"), "w"); out.write("block,li,usd,weth,side\n")
    legs = matched = 0; vol = mvol = 0.0
    tot = {"buy": [0.0, 0.0], "sell": [0.0, 0.0]}               # exact USD, day-close USD (matched legs)
    month = collections.defaultdict(lambda: [0.0, 0.0]); ratios = []
    for r in csv.reader(f):
        s, t, ts, v, b, tx, li = r[0], r[1], r[2], int(r[3]) / 1e9, int(r[4]), r[ti], int(r[li_])
        side = "buy" if venue(s) and t not in infra else "sell" if venue(t) and s not in infra else None
        if not side or v <= 0: continue
        legs += 1; vol += v
        x = sw.get(tx)
        if not x: continue
        w, g = (x[0], x[1]) if side == "buy" else (x[2], x[3])
        if not g: continue
        weth = (w / 1e18) / (g / 1e9); usd = weth * pe(ts)
        out.write(f"{b},{li},{usd:.6e},{weth:.6e},{side}\n")
        matched += 1; mvol += v; close = pa(ts)
        tot[side][0] += v * usd; tot[side][1] += v * close
        month[ts[:7]][0] += v * usd; month[ts[:7]][1] += v * close
        if close > 0: ratios.append(close / usd - 1)
    out.close()
ae = sorted(abs(x) for x in ratios)
chk = dict(legs=legs, matched=matched, coverageVol=round(100 * mvol / vol, 2) if vol else None,
           buy=dict(exactUsd=round(tot["buy"][0]), closeUsd=round(tot["buy"][1])), sell=dict(exactUsd=round(tot["sell"][0]), closeUsd=round(tot["sell"][1])),
           medianAbsErrPct=round(100 * ae[len(ae) // 2], 1) if ae else None, p90AbsErrPct=round(100 * ae[int(len(ae) * 0.9)], 1) if ae else None,
           months=[[m, round(a), round(c)] for m, (a, c) in sorted(month.items())])
json.dump(chk, open(os.path.join(D, "trades_check.json"), "w"))
print(f"trade_px.csv: {matched}/{legs} DEX legs priced exactly ({chk['coverageVol']}% of DEX volume) · buys exact ${chk['buy']['exactUsd']:,} vs day-close ${chk['buy']['closeUsd']:,} · "
      f"sells exact ${chk['sell']['exactUsd']:,} vs day-close ${chk['sell']['closeUsd']:,} · day-close error median {chk['medianAbsErrPct']}%, p90 {chk['p90AbsErrPct']}%")
