# Keeps data/bq/eth_flows.csv current without re-scanning the whole window every time.
#
#   python3 scripts/bq_flows.py cutoff   prints the newest transaction time in eth_flows.csv. The weekly BigQuery run
#                                        (bigquery/eth_flows_delta.sql) asks only for transactions AFTER it, a few GB
#                                        instead of ~220 GB. Every transaction of a study wallet up to that time is
#                                        already in the file, so nothing is counted twice.
#   python3 scripts/bq_flows.py merge    folds data/bq/eth_flows_delta.csv (if there is one) into eth_flows.csv, then
#                                        writes the file sorted by sender, receiver, so the daily commits stay small.
#
# Both files have one row per sender → receiver pair: f,t,n,eth,first,last,min_nonce. Merging a pair adds the counts
# and the ETH, and keeps the earliest first, the latest last and the lowest nonce. That is exact for every column, so
# a merged file equals what the full query would return for the same wallets, with one gap: a wallet that joined the
# study since the last full run is only covered from the cut-off on. The monthly full run (bigquery.yml) fills it in,
# and ethside.py never calls a wallet's first ETH what arrived after its own first transaction.
import csv, os, sys

BQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "bq")
COLS = ["f", "t", "n", "eth", "first", "last", "min_nonce"]


def read(path):
    out = {}
    with open(path) as fh:
        for r in csv.DictReader(fh):
            k = (r["f"].lower(), r["t"].lower())
            mn = int(float(r["min_nonce"])) if r.get("min_nonce") not in (None, "") else None
            row = [int(r["n"]), float(r["eth"]), r["first"][:19], r["last"][:19], mn]
            out[k] = merge_row(out[k], row) if k in out else row
    return out


def merge_row(a, b):
    nonce = min(x for x in (a[4], b[4]) if x is not None) if a[4] is not None or b[4] is not None else None
    return [a[0] + b[0], a[1] + b[1], min(a[2], b[2]), max(a[3], b[3]), nonce]


def merge(base, delta):
    out = dict(base)
    for k, row in delta.items():
        out[k] = merge_row(out[k], row) if k in out else row
    return out


def write(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLS)
        for (f, t), (n, eth, first, last, mn) in sorted(rows.items()):
            w.writerow([f, t, n, f"{eth:.12g}", first, last, "" if mn is None else mn])
    os.replace(tmp, path)


def cutoff(rows):
    return max((r[3] for r in rows.values()), default="")


if __name__ == "__main__":
    full, delta = os.path.join(BQ, "eth_flows.csv"), os.path.join(BQ, "eth_flows_delta.csv")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "cutoff":
        if not os.path.exists(full): sys.exit("no eth_flows.csv: run the full eth_flows query first")
        c = cutoff(read(full))
        if not c: sys.exit("eth_flows.csv is empty")
        print(c)
    elif cmd == "merge":
        if not os.path.exists(full): sys.exit("no eth_flows.csv to merge into")
        base = read(full)
        if os.path.exists(delta):
            d = read(delta)
            new = sum(1 for k in d if k not in base)
            rows = merge(base, d)
            os.remove(delta)
            print(f"eth_flows: {len(d)} pairs from the delta ({new} new) · {len(rows)} pairs · through {cutoff(rows)}")
        else:
            rows = base
            print(f"eth_flows: no delta · {len(rows)} pairs · through {cutoff(rows)}")
        write(full, rows)
    else:
        sys.exit("usage: bq_flows.py cutoff | merge")
