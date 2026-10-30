# Shared loader for the GME transfer archive + daily prices. Tokens in whole GME (decimals 9).
import csv, collections, bisect, os, pickle
D = os.path.join(os.path.dirname(__file__), "..", "data")
PAIR = "0x2aeee741fa1e21120a21e57db9ee545428e683c9"
V3POOL = "0x05391bd57d8c6fb30d9c39f6618f2207893922dc"
TOKEN = "0xc56c7a0eaa804f854b536a5f3d5f49d2ec4b12b8"
FOCUS = "0xe14767042159e5bd2bf16f81a0fe387ab153fbb4"
DEPLOYER = "0xe2cd830acc58d5a0e2f55cfedac116b793a2224f"
NULL = "0x0000000000000000000000000000000000000000"
DEAD = "0x000000000000000000000000000000000000dead"
SUPPLY = 420.69e9

def load():
    pk = os.path.join(D, "transfers.pkl")
    if os.path.exists(pk) and os.path.getmtime(pk) > os.path.getmtime(os.path.join(D, "transfers.csv")):
        return pickle.load(open(pk, "rb"))
    T = []
    for r in csv.reader(open(os.path.join(D, "transfers.csv"))):
        if r[0] == "sender": continue
        T.append((r[0], r[1], r[2], int(r[3]) / 1e9, int(r[4])))
    pickle.dump(T, open(pk, "wb"))
    return T

def prices(name="prices.csv"):
    px = {}
    for r in csv.reader(open(os.path.join(D, name))):
        if r[0] in ("day",): continue
        px[r[0]] = float(r[1])
    days = sorted(px)
    def at(d):
        d = d[:10]
        if d in px: return px[d]
        i = bisect.bisect_right(days, d)
        return px[days[i - 1]] if i else px[days[0]]
    return at

def index(T):
    by = collections.defaultdict(list)
    for i, t in enumerate(T):
        by[t[0]].append(i); by[t[1]].append(i)
    return by

def flows(T, by, a, since=None, until=None):
    a = a.lower(); ins = collections.defaultdict(lambda: [0.0, 0, None, None]); outs = collections.defaultdict(lambda: [0.0, 0, None, None])
    for i in by.get(a, []):
        s, r, ts, v, b = T[i]
        if since and ts < since: continue
        if until and ts > until: continue
        if r == a and s != a:
            e = ins[s]; e[0] += v; e[1] += 1; e[2] = e[2] or ts[:10]; e[3] = ts[:10]
        elif s == a and r != a:
            e = outs[r]; e[0] += v; e[1] += 1; e[2] = e[2] or ts[:10]; e[3] = ts[:10]
    return ins, outs

def balance_at(T, by, a, ts=None):
    b = 0.0
    for i in by.get(a, []):
        s, r, t, v, _ = T[i]
        if ts and t > ts: break
        if r == a: b += v
        if s == a: b -= v
    return b
