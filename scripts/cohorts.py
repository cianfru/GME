# Early-holder cohorts: who arrived when, how much they took, did they sell into the top, are they still here,
# and what have they done in the last 30/90 days. Wallet-level (no entity merge), infra excluded.
import sys, json, collections, os, datetime
sys.path.insert(0, os.path.dirname(__file__))
from txlib import *
T = load(); by = index(T); pa = prices()
EX = json.load(open(os.path.join(D, "exclude.json"))); infra = set(EX); CEX = {a for a, v in EX.items() if v["kind"] == "cex"}
bundle = set(json.load(open(os.path.join(D, "launch_tree.json")))["tree"])
NOW = T[-1][2]
def ago(days): return (datetime.datetime.fromisoformat(NOW.replace("Z", "")) - datetime.timedelta(days=days)).isoformat() + "Z"
T30, T90 = ago(30), ago(90)
TOP0, TOP1 = "2024-10-15", "2025-01-31"   # the run to the Dec-2024 ATH and its plateau
st = {}
for s, r, ts, v, b in T:
    for a, sign in ((s, -1), (r, 1)):
        if a in infra: continue
        w = st.get(a)
        if w is None:
            w = st[a] = dict(first=ts, firstSrc=None, bal=0.0, peak=0.0, bought=0.0, buyUsd=0.0, sold=0.0, sellUsd=0.0, soldTop=0.0, soldTopUsd=0.0, d30=0.0, d90=0.0, b30=0.0, s30=0.0, b90=0.0, s90=0.0)
        if sign > 0 and w["firstSrc"] is None: w["firstSrc"] = s
        w["bal"] += sign * v; w["peak"] = max(w["peak"], w["bal"])
        other = r if sign < 0 else s
        mkt = other in infra and other not in CEX and other not in (NULL,)
        p = pa(ts)
        if mkt and sign > 0: w["bought"] += v; w["buyUsd"] += v * p
        if mkt and sign < 0:
            w["sold"] += v; w["sellUsd"] += v * p
            if TOP0 <= ts[:10] <= TOP1: w["soldTop"] += v; w["soldTopUsd"] += v * p
        if ts >= T90:
            w["d90"] += sign * v
            if mkt: w["b90" if sign > 0 else "s90"] += v
        if ts >= T30:
            w["d30"] += sign * v
            if mkt: w["b30" if sign > 0 else "s30"] += v
LAUNCH = "2024-05-13T03:45:23Z"
def cohort(a, w):
    t = w["first"]
    if a in bundle: return "0 launch bundle"
    if t < "2024-05-14T03:45:23Z": return "1 day 1"
    if t < "2024-05-20T03:45:23Z": return "2 week 1"
    if t < "2024-06-13": return "3 month 1"
    if t < "2024-10-01": return "4 Jun–Sep 2024"
    if t < "2025-02-01": return "5 the run (Oct 24–Jan 25)"
    if t < "2026-01-01": return "6 2025"
    return "7 2026"
C = collections.defaultdict(lambda: collections.Counter())
DUST = 1e6   # 1M GME (~$6 today) — below this a wallet is "gone"
for a, w in st.items():
    if w["peak"] < 10e6: continue          # never held ≥10M GME (~$60 today, $4k at ATH) — ignore dust
    c = C[cohort(a, w)]
    c["wallets"] += 1; c["peakSum"] += w["peak"]; c["bought"] += w["bought"]; c["buyUsd"] += w["buyUsd"]; c["sellUsd"] += w["sellUsd"]
    c["holdNow"] += w["bal"] > DUST; c["balNow"] += max(w["bal"], 0)
    c["soldTopUsd"] += w["soldTopUsd"]; c["soldAtTop"] += w["soldTopUsd"] > 1000
    c["add90"] += w["d90"] > 1e6; c["cut90"] += w["d90"] < -1e6; c["net90"] += w["d90"]; c["netBuy90"] += w["b90"] - w["s90"]
    c["add30"] += w["d30"] > 1e6; c["cut30"] += w["d30"] < -1e6; c["net30"] += w["d30"]
print(f"as of {NOW[:16]} · wallets that ever held ≥10M GME, by when they first got GME")
print("cohort".ljust(30), "wallets  still-hold  %wallets  held-now(B) %supply  bought$   sold$   sold-into-top$ (n)   90d: add/cut  net(B)  | 30d add/cut net(B)")
out = {}
for k in sorted(C):
    c = C[k]
    out[k] = dict(c)
    print(k.ljust(30), str(c["wallets"]).rjust(6), str(c["holdNow"]).rjust(9), f"{100*c['holdNow']/c['wallets']:7.0f}%", f"{c['balNow']/1e9:10.2f}", f"{100*c['balNow']/SUPPLY:7.2f}%", f"{c['buyUsd']/1e6:7.2f}M", f"{c['sellUsd']/1e6:6.2f}M", f"{c['soldTopUsd']/1e6:9.2f}M ({c['soldAtTop']})", f"{c['add90']:5}/{c['cut90']:<4}", f"{c['net90']/1e9:6.2f}", "|", f"{c['add30']}/{c['cut30']}", f"{c['net30']/1e9:.2f}")
json.dump({"asOf": NOW, "cohorts": out}, open(os.path.join(D, "cohorts.json"), "w"))
json.dump(st, open(os.path.join(D, "wallet_state.json"), "w"))
