# Runs the study queries in bigquery/*.sql against the public Ethereum dataset, cheaply and safely:
#   every query is first a DRY RUN (free) that reports how many bytes it would scan;
#   with DRY=false it runs only if that is under MAX_GB, and BigQuery itself refuses to bill more (maximum_bytes_billed).
# Results go to data/bq/<query>.csv; the byte counts to data/bq/run.json (shown on the site's Methodology page).
#   env: GCP_PROJECT, BQ_DATASET (default gme_study), DRY (default true), MAX_GB (per query, default 250), QUERIES (comma list)
import subprocess, json, os, sys, datetime
P = os.environ["GCP_PROJECT"]; DS = os.environ.get("BQ_DATASET", "gme_study")
DRY = os.environ.get("DRY", "true").lower() != "false"; CAP = int(float(os.environ.get("MAX_GB", "250")) * 1e9)
QS = [q for q in os.environ.get("QUERIES", "eth_flows,first_funder,token_footprint,tx_signers").split(",") if q]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "bq"); os.makedirs(OUT, exist_ok=True)
RJ = os.path.join(OUT, "run.json")
run = json.load(open(RJ)) if os.path.exists(RJ) else {}
bq = ["bq", f"--project_id={P}", "query", "--use_legacy_sql=false", "--location=US"]
total = 0
for q in QS:
    sql = open(os.path.join(os.path.dirname(OUT), "..", "bigquery", f"{q}.sql")).read().replace("{P}", P).replace("{DS}", DS)
    d = subprocess.run(bq + ["--dry_run", "--format=json", sql], capture_output=True, text=True)
    if d.returncode: print(f"{q}: dry run failed\n{d.stderr or d.stdout}"); run[q] = dict(error=(d.stderr or d.stdout)[-400:]); continue
    try: nb = int(json.loads(d.stdout)["statistics"]["totalBytesProcessed"])
    except Exception: nb = int("".join(ch for ch in d.stdout.split("process")[-1] if ch.isdigit()) or 0)
    rec = dict(bytes=nb, gb=round(nb / 1e9, 1), at=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), ran=False)
    print(f"{q}: would scan {nb/1e9:.1f} GB")
    if not DRY:
        if nb > CAP: print(f"  skipped: above the {CAP/1e9:.0f} GB cap"); rec["skipped"] = "above cap"
        else:
            path = os.path.join(OUT, f"{q}.csv")
            with open(path, "w") as f:
                r = subprocess.run(bq + ["--format=csv", "--max_rows=5000000", f"--maximum_bytes_billed={CAP}", sql], stdout=f, stderr=subprocess.PIPE, text=True)
            if r.returncode: print(f"  FAILED: {r.stderr[-600:]}"); rec["error"] = r.stderr[-400:]
            else:
                rows = sum(1 for _ in open(path)) - 1; rec.update(ran=True, rows=rows); total += nb
                print(f"  ran: {rows} rows → data/bq/{q}.csv")
    run[q] = rec
json.dump(run, open(RJ, "w"), indent=1)
print(f"{'dry run only' if DRY else 'billed'}: {sum(r.get('bytes', 0) for k, r in run.items() if k in QS)/1e9:.1f} GB measured, {total/1e9:.1f} GB run")
