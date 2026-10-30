# gme_terminal

On-chain study and daily watch for **GME on Ethereum** (`0xc56C7A0eAA804f854B536A5F3D5f49D2EC4B12b8`, 9 decimals).

Everything is rebuilt from the public transfer history, with free data only. There are no API keys and no paid quota. Every number can be checked against a block explorer.

## What runs every day

`.github/workflows/daily.yml` runs at 06:23 UTC. You can also start it by hand from the Actions tab ("Run workflow").

1. Downloads the full transfer archive. It is a release asset (tag `gme-archive`), not stored in git. On the first run there is no asset yet, so the workflow pulls the whole history from the deploy block, which takes about 15 minutes.
2. Pulls only the new transfers through public Ethereum nodes (`eth_getLogs`), then merges them into the archive.
3. Refreshes daily GME and ETH prices from DeFiLlama.
4. Checks every new address to see whether it is a contract or a person's wallet, then rebuilds the exclude list (pools, routers, exchanges, burns).
5. Rebuilds the clusters:
   - the focus wallet's group;
   - the Coinbase-funded group;
   - every other multi-wallet group;
   - fresh holding wallets fed by buy-and-forward wallets.
6. Finds quiet accumulators: owners who added at least 0.1% of supply in the last 90 days and sold less than 15% of it.
7. Runs the metrics engine: realized price, MVRV, cost-basis distribution and holding age.
8. Runs the watch: it compares every watched group with the previous run and writes the alerts.
9. Uploads the grown archive and commits `data/`.

## Where to read the output

- `data/alerts/latest.json`: the latest run's alerts. The same text is in the run's summary on the Actions page.
- `data/alerts/log.jsonl`: one line per run.
- `data/stealth.json`: the current quiet-accumulator list.
- `data/vaults90.json`: fresh holding wallets and the wallets that feed them.
- `data/focus_cluster.json`: the focus wallet's cluster.
- `data/coinbase_group.json`: the Coinbase-funded group.
- `data/float.json`: who holds the supply, by group.
- `data/market.json`: holder counts, plus buyers and sellers over 30, 90 and 180 days.
- `data/engine/onchain.json` and `data/engine/urpd.json`: the metrics series and the cost-basis histogram.
- `report/gme-study.html`: the full written study.

### Alert levels

- **high**: a watched group sent at least 0.05% of supply to an exchange or sold it on a DEX.
- **medium**: a new holding wallet or a new accumulator appeared, or a watched group moved coins to other wallets.
- **info**: buys, and changes in the pool.

## The website (Vercel)

`site/index.html` is a dashboard that reads `site.json`. `scripts/build-site.mjs` builds that file from `data/`, and Vercel runs it on every push to `main`. That means every daily data commit redeploys the site. The dashboard shows:
- the latest alerts and the alert history;
- the quiet accumulators;
- the buy-and-hide holding wallets, including whether each one still holds;
- the watched groups and who holds the supply;
- buyers and sellers on the DEX.

The full study is served at `/study`.

**Password (optional).** The site is open to anyone with the URL (and asks search engines not to index it). To lock it, set `SITE_PASSWORD` in the Vercel project's environment variables and redeploy: `middleware.js` then asks for that password (any username) on every page and data file.

Build and preview locally:
```
npm install
node scripts/build-site.mjs              # → dist/
python3 -m http.server --directory dist  # http://localhost:8000 (no password check locally)
npm test                                 # password-check tests
```

## Run it locally

```
python3 scripts/pull-transfers-rpc.py --start-block=19858481 --out=data/transfers.csv   # full history, ~15 min
python3 scripts/pull-prices-defillama.py --out=data/prices.csv
python3 scripts/pull-eth-prices.py data/eth_prices.csv
```

Then run the same steps, in order, as `daily.yml`. Every script reads from and writes to `data/`.

## Limits

- Wallet linking only uses transfers of GME itself, plus ETH sent to wallets that are already watched. Two wallets funded by the same exchange are never linked.
- Groups are a lower bound on what one person controls. Nothing here proves who owns a wallet.
- Nothing here is financial advice.
