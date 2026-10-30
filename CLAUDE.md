# gme_terminal: project guide

An on-chain study and daily watch for **GME on Ethereum**. It follows the method of the pepecoin and SPX6900 terminals:
- rebuild every wallet's balance and cost from the public transfer history;
- publish the method;
- label the limits.

Read this file first. It is enough to continue without the original conversation.

## 1. Rules (same as the sibling projects)

- **Every number must be checkable.** Use free public data only (public RPC, DeFiLlama, Blockscout, Ethplorer). No paid quota.
- **Reads describe positions, never buy or sell signals.** Nothing here is financial advice.
- **Never guess an exclude address.** Wrongly excluding or merging wallets overstates control by a few hands.
- **Groups are a floor, not a ceiling.** Linking errs toward NOT merging. A group that grows past 60 wallets gets a flag and is never trusted.
- **Match the contract address, never the ticker.** Fake "GME" tokens exist. MEXC's GME is the Solana token, not this one.

## 2. The token

| Item | Value |
|---|---|
| Contract | `0xc56C7A0eAA804f854B536A5F3D5f49D2EC4B12b8` |
| Decimals | **9** |
| Supply | 420.69B |
| Deployer | `0xe2cd830acc58d5a0e2f55cfedac116b793a2224f` |
| First transfer | block 19,858,481 (2024-05-13) |
| Contract settings | renounced, 0% tax |
| Main pool | Uniswap V2 pair `0x2aeee741…83c9`, token0 = WETH, LP 100% burned |
| Other pool | V3 pool `0x05391bd5…` (1% fee), tiny |
| Exchange listings | none live for this token (Gate delisted it) |

- **Focus wallet:** `0xE14767042159E5BD2bf16F81A0FE387ab153Fbb4`. The person behind it has a following on X and has supported the project since launch.
- **Scale:** about 470k transfers and about 11.4k holders. The full pull takes about 15 minutes and the whole pipeline runs in a few minutes.

## 3. Pipeline (`.github/workflows/daily.yml`, daily at 06:23 UTC plus manual runs)

1. **Archive.** The full transfer history (`sender,receiver,time,value,block`) is a release asset, tag `gme-archive`, not in git. The first run has no asset and seeds it with a full pull. `archive_tools.py merge` replaces from the first block of the new pull onward, so re-pulling the boundary block is safe.
2. **`pull-transfers-rpc.py`** uses `eth_getLogs` on drpc and mevblocker. Both add `blockTimestamp` to each log, so no block lookups are needed. Error codes 403, 429 and 413 mean "shrink the range".
3. **Prices.** `pull-prices-defillama.py` fetches GME and `pull-eth-prices.py` fetches ETH. ⚠ DeFiLlama's daily stamp is the previous day's close, so analysis windows are shifted by one day.
4. **`getcode.py`** sorts new addresses into contract or wallet. EIP-7702 accounts (code `0xef0100…`) count as **people**, not contracts.
5. **`build_exclude.py`** writes `data/exclude.json`. It covers pools, routers, contracts and exchanges:
   - MEXC 2 `0x9642…`
   - MEXC sweeper `0x3cc936b7`
   - Gate `0x0d0707…`
   - two unidentified exchanges, `0x8fca4ade` and `0xf81b45b1`
   
   Exchange labels come from `data/eth_labels.csv`.
6. **Clusters:**
   - `cluster.py` builds the focus wallet's cluster (`focus_cluster.json`).
   - `coinbase_group.py` builds the Coinbase-funded group: everyone who sent to collector `0xe1fc21df…5717`.
   - `cluster_all.py` builds every other multi-wallet group.
   - `vaults90.py` finds fresh holding wallets fed by buy-and-forward wallets.
7. **`stealth.py`** finds quiet accumulators. It runs, then `funders_ethplorer.py` fetches gas funders, then it runs again with gas links.
8. **`float.py`, `market.py`, `overhang.py`** build supply by group, holders and flows, and exchange overhang.
9. **Engine.** `build-onchain-local.mjs`, ported from SPX and pepecoin, runs with `--decimals=9 --daily`. It produces realized price, MVRV, URPD and holding-age bands. Its console still says "SPX" in places; that is cosmetic.
10. **`watch.py`** compares every watched group with the last run (`data/watch_state.json`). It writes `data/alerts/latest.json` and `log.jsonl`, and puts the same text in the Actions run summary.

### Website (Vercel)
- **A scrolling "visual journey", not a dashboard** (owner asked for "a visual journey, not text heavy"). `site/index.html` has 12 chapters, one per screen. Each has a short headline with the key number, one big D3 visual, and at most one line of caption:
  1. price story, with pumps marked;
  2. launch waffle;
  3. focus wallet holdings + price;
  4. the 70-wallet network (force graph);
  5. monthly sends to exchanges vs price;
  6. pool calculator ("buy $X → +Y%");
  7. supply split bar;
  8. cost-basis (URPD) underwater chart;
  9. cohort survival;
  10. quiet-accumulator bubbles;
  11. buy-and-hide received vs held;
  12. today's alerts as cards, then the verdict (pros/cons, watched signals).
  
  Tables sit in a collapsed "All the numbers" block (the accessible view). Charts render lazily as each chapter scrolls in.
- **Data:** `scripts/journey.py` (daily, after cohorts.py) writes `data/journey.json`. It holds:
  - daily price and ATH;
  - daily balance of the focus wallet and of the cluster;
  - the cluster's monthly USD sent to exchanges (CEX + deposit-like addresses);
  - live pool reserves via `getReserves()`;
  - the cluster graph (members + evidence links between members);
  - URPD buckets, cohorts, the launch steps and pump runs.
  
  The last two come from static history files (`page_data.json`, `runs.json`, `launch_block0.json`). `scripts/build-site.mjs` folds it all into `dist/site.json`, along with alerts, accumulators, holding wallets, groups and float.
- **Charts follow the dataviz rules:**
  - the reference palette (validated light + dark);
  - one y-axis per panel: price always gets its own panel under a shared x, never a dual axis;
  - hover tooltips;
  - a legend on every multi-series chart.
- `vercel.json`: no framework, build command `node scripts/build-site.mjs`, output `dist`. Each push to `main`, including the daily data commit, redeploys.
- **Password is optional (owner: "keep it simple, a side project").** `middleware.js` adds HTTP Basic auth only when the `SITE_PASSWORD` env var is set (any username). Without it the site is open, and `noindex` keeps it out of search. Tests: `npm test`.
- **Freshness:** the "Data as of" badge turns red after 36 hours.
- **"Still holding"** (a buy-and-hide wallet) means it kept ≥80% of what it received AND sold or deposited ≤20% of it. A trader that refills, like `0x859f…d9d1` which sold 3.3B, is not a hider.

## 4. Linking rules (what makes two wallets one owner)

Each rule below links two wallets:
- **seed:** the first GME a wallet ever received (at least $2k worth) came from the other wallet.
- **drain:** a wallet sent at least 90% of its balance (at least $2k worth) to the other.
- **shared exchange deposit address:** both used the same deposit address. Only counts when 2 to 10 wallets share it, and the address forwards at least 95% to an exchange.
- **ethfund:** the focus wallet sent at least 0.1 ETH to the other wallet.
- **gas link:** one sent the other at least 0.001 ETH, and **both** wallets are already on the watchlist.

Guards:
- Any address that seeds more than 40 wallets is a hub, so no links go through it.
- A group of more than 60 wallets is flagged and not trusted.
- **A shared exchange or relayer funder never links anyone.** An earlier "same first funder" rule was removed because those funders were exchanges.
- Tiny "address poisoning" transfers never link anyone.

## 5. Findings (snapshot 2026-10-30, price ≈ $6.4e-6, market cap ≈ $2.7M)

- **Launch:** 27 wallets funded by 2 addresses took **42% of supply for 2.5 ETH** at launch and sold all of it.
- **The focus wallet's cluster:**
  - 69 to 70 wallets holding **64.7B (15.4%)**, or up to 20.7% if a looser extension is counted.
  - The main wallet has never sold on a DEX.
  - The cluster sent about **$2.67M** of GME to exchanges, about $2.0M of it near the top.
  - One MEXC deposit address is shared by 6 of its wallets.
  - 38.8B was shuffled between wallets on 24–25 Sep 2025.
- **Coinbase group:** 31 wallets holding 8.46B. They spent about $420k and are down about 89%.
- **Pool:** 138 WETH against 49.4B GME.
  - Price moves with the square of the ETH reserve.
  - Buying **1% of supply costs about $29k and lifts price about 19%**.
- **Quiet accumulators (90 days):** 14 owners added 16.1B (3.8% of supply) for about $97k. Worth watching:
  - `0x53ee…cefdb`: 6 wallets, +3.24B, about $25k.
  - `0xf0f7 + 0x1935 + 0x3e2d`, plus feeder `0x574b`: about 4.0B held, about $23k.
  - `0xf48e…fd58`: holds 4.17B.
  - `0x05e4…0814`: 1.48B withdrawn from MEXC.
  - `0x4553…4ea2`: buys arriving from other chains.
  - `0xfa67…dbb6`: has held since launch day, 7.11B.
- **Buy-and-hide holding wallets:**
  - 18 fresh wallets received coins this way in the last 90 days, but **only 4 still hold them**.
  - Holding: `0x53ee…efdb` 3.44B, `0xf0f7…b749` 1.50B, `0x644a…7982` 0.80B and `0xb9f4…1813` (small).
  - Several were relays that sold on the DEX: `0xc71f…` 1.49B and `0x8d56…` 0.93B, both in the 90-day top sellers.
  - Three small ones went to exchanges.
  - `vaults90.py` now records `bal`, `soldDex`, `toCex` and `sent` for each, so the page shows which is which. Judge a holding wallet by what it still holds, not by what it received.
- **First watch run (24 hours to 2026-10-30):**
  - the focus cluster took 1.25B from an exchange and bought 0.69B on the DEX;
  - accumulators `0x4553`, `0x7465` and `0xfa67` bought on the DEX;
  - no high-level alerts.

The full write-up is `report/gme-study.html` (also published as a private claude.ai page).

## 6. Lessons learned (don't repeat)

- **Blockscout's API now returns 429 almost every time.** Use Ethplorer's free key (`getAddressTransactions`, 0.7 s pacing) for ETH funders. `bs.py` prints a warning instead of crashing.
- **Uniswap V3 liquidity deposits are not sales.** Keep the V3 pool and the positions NFT contract in the liquidity set.
- **Never `pkill -f` with a pattern that also appears in the same command.** It kills its own shell.
- **Gate's and MEXC's websites block scripts.** Check listings through their APIs. Bybit's API is blocked by region from here.
- **"Buy and hide" looks like this:** a fresh wallet buys on the DEX, then forwards at least 80% to a holding wallet that never sells. At a $2.7M market cap, $10k to $20k in that pattern is someone building a position. Watch for it.

## 7. Next ideas

- Track whether the accumulators' holding wallets ever send to an exchange. That is the exit tripwire.
- Trace accumulators' ETH funding one or two hops back to see whether one source funds several of them.
- If wanted, send alerts somewhere other than the run summary (an issue comment or email).
