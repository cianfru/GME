# Crowd behaviour: who is buying, who is leaving, who is still here, and what proven winners do now.
#   data/crowd.json — daily series aligned with terminal.json's days, cohort survival, smart-money table.
#
# The unit is the OWNER: an entity from data/entities.json counts as one unit, any other wallet as its own unit.
# Moves between an entity's wallets never count as buying, selling or leaving.
# Market flows only: a buy = GME arriving from the DEX or an exchange; a sale = GME going to the DEX or an exchange.
#   Buyers are classed new (the unit never held GME), returning (it held before but was empty, ≤1M GME) or adding.
#   Sellers are classed exit (≤1M GME left after the sale) or partial; and in profit or at a loss against the unit's
#   average cost. Average cost: every inflow from outside the unit at that day's price (transfers in included);
#   a transfer out to another owner lowers the cost basis in proportion, a sale realizes profit or loss.
# Cohorts: units by the quarter they first received GME; how many still hold >1M GME at each month end.
# Smart money: units whose realized profit is ≥ $5k AND ≥ 100% of what the sold coins cost. Their buying and selling
# since is a HINDSIGHT read: they are picked by today's record.
import sys, json, os, collections, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import *

DUST = 1e6
SM_USD, SM_ROI = 5000.0, 1.0
T = load(); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}; infra = set(EX)
LP = {V3POOL, "0xc36442b4a4522e871399cd717abdd847ab11fe88"}
outs = collections.defaultdict(lambda: collections.defaultdict(float))
for s, r, ts, v, b in T: outs[s][r] += v
deplike = {a for a, o in outs.items() if a not in infra and sum(o.values()) > 0 and sum(x for k, x in o.items() if k in CEX) / sum(o.values()) >= 0.95}
is_dex = lambda a: a in infra and a not in CEX and a not in LP and a not in (NULL, DEAD, TOKEN)
is_cex = lambda a: a in CEX or a in deplike
REG = json.load(open(os.path.join(D, "entities.json"))) if os.path.exists(os.path.join(D, "entities.json")) else {"entities": []}
unit_of, uname = {}, {}
for e in REG["entities"]:
    for a in e["members"]: unit_of[a] = "e:" + e["id"]
    uname["e:" + e["id"]] = e["name"]
U = lambda a: unit_of.get(a, a)
wallet = lambda a: a not in infra and a not in deplike

NOW = T[-1][2]; TODAY = NOW[:10]
day0 = datetime.date.fromisoformat(T[0][2][:10]); day1 = datetime.date.fromisoformat(TODAY)
days = [(day0 + datetime.timedelta(days=i)).isoformat() for i in range((day1 - day0).days + 1)]
ix = {d: i for i, d in enumerate(days)}; N = len(days)
z = lambda: [0.0] * N
K = ["buyNew", "buyRet", "buyAdd", "nNew", "nRet", "nAdd", "sellPart", "sellExit", "nPart", "nExit", "sellProfit", "sellLoss", "realized",
     "buyNewUsd", "buyRetUsd", "buyAddUsd", "sellProfitUsd", "sellLossUsd"]
S = {k: z() for k in K}
seen_day = collections.defaultdict(set)
ubal = collections.Counter(); ucost = collections.Counter(); held = set(); first = {}
realized = collections.Counter(); cost_sold = collections.Counter(); bought_usd = collections.Counter(); sold_usd = collections.Counter()
last_buy, last_sell = {}, {}
last_ev = collections.defaultdict(dict)                              # class → unit → last day it did that (distinct counts per window)
# cohort snapshots at each month end
months = sorted({d[:7] for d in days})
month_end = {m: max(d for d in days if d[:7] == m) for m in months}
snap_days = set(month_end.values())
coh = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0.0]))

def snapshot(m):
    for u, b in ubal.items():
        if u in first and b > DUST:
            q = first[u][:4] + " Q" + str((int(first[u][5:7]) - 1) // 3 + 1)
            x = coh[q][m]; x[0] += 1; x[1] += b

cur_day = None
for s, r, ts, v, blk in T:
    d = ts[:10]
    if cur_day is not None and d != cur_day and cur_day in snap_days: snapshot(cur_day[:7])
    cur_day = d
    i = ix[d]; px = pa(ts)
    us, ur = (U(s) if wallet(s) else None), (U(r) if wallet(r) else None)
    if us is not None and us == ur: continue                         # inside one owner: nothing happens
    if ur is not None:
        before = ubal[ur]
        if is_dex(s) or is_cex(s):                                  # market buy (DEX or exchange withdrawal)
            cls = "New" if ur not in held else "Ret" if before <= DUST else "Add"
            S["buy" + cls][i] += v; S["buy" + cls + "Usd"][i] += v * px
            key = (cls, ur)
            if key not in seen_day[i]: seen_day[i].add(key); S["n" + cls][i] += 1
            bought_usd[ur] += v * px; last_buy[ur] = d; last_ev[cls][ur] = d
        ubal[ur] += v; ucost[ur] += v * px; held.add(ur); first.setdefault(ur, d)
    if us is not None:
        b0 = ubal[us]; avg = ucost[us] / b0 if b0 > 0 else px
        q = min(v, max(b0, 0.0))
        if is_dex(r) or is_cex(r):                                  # market sale (DEX or exchange deposit)
            after = b0 - v
            ex = after <= DUST
            S["sellExit" if ex else "sellPart"][i] += v
            key = ("X" if ex else "P", us)
            if key not in seen_day[i]: seen_day[i].add(key); S["nExit" if ex else "nPart"][i] += 1
            pl = (px - avg) * q
            if px >= avg: S["sellProfit"][i] += v; S["sellProfitUsd"][i] += v * px
            else: S["sellLoss"][i] += v; S["sellLossUsd"][i] += v * px
            last_ev["Exit" if ex else "Part"][us] = d
            S["realized"][i] += pl; realized[us] += pl; cost_sold[us] += avg * q; sold_usd[us] += v * px; last_sell[us] = d
        ucost[us] -= avg * q
        ubal[us] = b0 - v
        if ubal[us] <= 0: ubal[us] = 0.0; ucost[us] = 0.0
if cur_day in snap_days or True: snapshot(TODAY[:7])

# ---- cohorts ----
cohorts = []
for q in sorted(coh):
    arrived = sum(1 for u, f in first.items() if f[:4] + " Q" + str((int(f[5:7]) - 1) // 3 + 1) == q)
    ser = [[m, coh[q][m][0], round(coh[q][m][1] / 1e9, 3)] for m in months if m >= q[:4] + "-" + str((int(q[-1]) - 1) * 3 + 1).zfill(2)]
    cohorts.append(dict(name=q, arrived=arrived, series=ser))

# ---- smart money (owners with a proven realized record), and what they did lately ----
spot = pa(NOW); c7 = (day1 - datetime.timedelta(days=7)).isoformat(); c30 = (day1 - datetime.timedelta(days=30)).isoformat(); c90 = (day1 - datetime.timedelta(days=90)).isoformat()
smart = {u for u in realized if realized[u] >= SM_USD and cost_sold[u] > 0 and realized[u] / cost_sold[u] >= SM_ROI}
flow = {u: collections.Counter() for u in smart}
sm_buy, sm_sell = z(), z()
for s, r, ts, v, blk in T:
    if ts[:10] < c90: continue
    us, ur = (U(s) if wallet(s) else None), (U(r) if wallet(r) else None)
    if us == ur: continue
    i = ix[ts[:10]]; usd = v * pa(ts)
    if ur in smart and (is_dex(s) or is_cex(s)):
        sm_buy[i] += usd
        for k, c in (("7", c7), ("30", c30), ("90", c90)):
            if ts[:10] > c: flow[ur]["b" + k] += usd
    if us in smart and (is_dex(r) or is_cex(r)):
        sm_sell[i] += usd
        for k, c in (("7", c7), ("30", c30), ("90", c90)):
            if ts[:10] > c: flow[us]["s" + k] += usd
rows = []
for u in smart:
    b = ubal[u]
    rows.append(dict(u=u if not u.startswith("e:") else None, eid=u[2:] if u.startswith("e:") else None, name=uname.get(u), realized=round(realized[u]),
                     roi=round(realized[u] / cost_sold[u], 2), boughtUsd=round(bought_usd[u]), soldUsd=round(sold_usd[u]), bal=round(b), avg=(ucost[u] / b if b > DUST else None),
                     valueUsd=round(b * spot), net7=round(flow[u]["b7"] - flow[u]["s7"]), net30=round(flow[u]["b30"] - flow[u]["s30"]), net90=round(flow[u]["b90"] - flow[u]["s90"]),
                     lastBuy=last_buy.get(u), lastSell=last_sell.get(u)))
rows.sort(key=lambda x: -x["realized"])
r2 = lambda a, n=4: [round(x / 1e9, n) for x in a]
daily = {k: (r2(S[k]) if not k.startswith("n") and not k.endswith("Usd") and k != "realized" else [round(x) for x in S[k]]) for k in K}
daily["smBuyUsd"], daily["smSellUsd"] = [round(x) for x in sm_buy], [round(x) for x in sm_sell]
win = {}
for nd in (7, 30, 90, 365, 100000):
    c = (day1 - datetime.timedelta(days=nd)).isoformat()
    win[str(nd) if nd < 100000 else "all"] = {k.lower(): sum(1 for x in last_ev[k].values() if x > c) for k in ("New", "Ret", "Add", "Exit", "Part")}
out = dict(asOf=NOW, win=win, d0=days[0], d1=days[-1], dust=DUST, smartRule=dict(usd=SM_USD, roi=SM_ROI), daily=daily, cohorts=cohorts,
           smart=dict(n=len(rows), holding=sum(1 for x in rows if x["bal"] > DUST), heldGme=round(sum(x["bal"] for x in rows)), rows=rows[:60]),
           units=dict(total=len(first), holding=sum(1 for u, b in ubal.items() if b > DUST)))
json.dump(out, open(os.path.join(D, "crowd.json"), "w"))
L = lambda k, n: sum(S[k][-n:])
print(f"crowd.json: {N} days · units ever {len(first)}, holding {out['units']['holding']} · 30d buys new/ret/add {L('buyNew',30)/1e9:.2f}/{L('buyRet',30)/1e9:.2f}/{L('buyAdd',30)/1e9:.2f}B · "
      f"30d sells partial/exit {L('sellPart',30)/1e9:.2f}/{L('sellExit',30)/1e9:.2f}B (profit {L('sellProfit',30)/1e9:.2f}B) · smart money {len(rows)} owners, {out['smart']['holding']} holding")
