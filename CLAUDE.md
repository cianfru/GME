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
- **Names (owner, 2026-11-08):** the focus wallet's group is called **"fbb4"** everywhere visible (his X name and the end of his wallet); the wallet itself is "fbb4's main wallet". Every other group is called by a **handle**: the last four characters of the wallet it is named after, one more character if two would clash, kept from run to run: "Accumulator efdb", "Holding wallet b749", "Sep-2025 wallet 94f4", "Linked group 847d"; "Coinbase group" keeps its name (handle 5717). On the site the handle is shown in gold monospace. One rule in three places: `entities.py` (stores `tag` + `anchor` per entity), `groups.py` `display()` / `namer()` (Python text) and `relabel` in `build-site.mjs`. The watch files keep their raw keys ("Your wallet's cluster", "Accumulator 0x53ee…efdb"), so history stays continuous; only display text changes. In code the word "focus" stays (`FOCUS`, kind `focus`).
- **Scale:** about 470k transfers and about 11.4k holders. The full pull takes about 15 minutes and the whole pipeline runs in a few minutes.

## 3. Pipeline (`.github/workflows/daily.yml`: full daily at 06:23 UTC, light every 4 hours, plus manual runs)

1. **Archive.** The full transfer history (`sender,receiver,time,value,block,tx,li`: tx hash + log index since 2026-11-07) and the GME pools' swap history (`swaps.csv`: `pool,time,block,li,tx,wethIn,wethOut,gmeIn,gmeOut`, raw integers, WETH = token0 in both pools) are release assets, tag `gme-archive`, not in git. An archive without the `tx` column, or a missing `swaps.csv.gz`, triggers one automatic full re-pull (~20 min). The first run has no asset and seeds it with a full pull. `archive_tools.py merge` replaces from the first block of the new pull onward, so re-pulling the boundary block is safe.
2. **`pull-transfers-rpc.py`** uses `eth_getLogs` on drpc and mevblocker; one call per block range returns the GME Transfer logs AND the Swap logs of the V2 pair and V3 pool (`--swaps=`). Both add `blockTimestamp` to each log, so no block lookups are needed. Error codes 403, 429 and 413 mean "shrink the range".
3. **Prices.** `pull-prices-defillama.py` fetches GME and `pull-eth-prices.py` fetches ETH. ⚠ DeFiLlama's daily stamp is the previous day's close, so analysis windows are shifted by one day.
   - **Exact trade prices (`trades.py`, 2026-11-07):** per transaction, buy price = WETH into the pools ÷ GME out, sell price = WETH out ÷ GME in; every pool/router ↔ wallet GME transfer in that tx gets it, × the day's ETH close → `data/trade_px.csv` (rebuilt each run, not committed) + `data/trades_check.json`. First run: 217,790 of 227,461 DEX legs, **99.3% of DEX volume**; the day's GME close was off by a median **6.9%** per trade (p90 60%). `txlib.exact_prices(T, pa)` gives a per-transfer price list (exact for DEX legs, else day close); used by `entities.py` (cost basis), `crowd.py` (owner cost, P/L, smart money: 439 → 511 owners) and `terminal.py` (DEX $ flows, wallet histories). The cost engine (realized price, MVRV, URPD) still uses the day's close; linking-rule thresholds too.
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

### Website (Vercel): a monitoring terminal
- **What the owner wants (2026-10-30):** a terminal to visit regularly and *see what's happening*, like the SPX/pepecoin work. Not a story: an earlier scrolling "visual journey" version was rejected. `site/index.html` is one static page, D3 v7 from cdnjs, dark by default with a light toggle.
- **Look (owner, 2026-11-05 redesign, supersedes the 2026-10-31 type rules):** a premium on-chain intelligence terminal.
  - **Glass panels over a coloured background, sharp corners.** The background is a deep navy with gold / blue / teal glows and a faint grid (`--bg-grad`, fixed). Panels are frosted glass (`backdrop-filter`), square, with small corner brackets (`.panel::after`); the key panel of a page gets gold brackets (`.key`). Owner asked for glassmorphism + sharp angles + a background colour explicitly.
  - **Two families from one designer:** **Geist** for text, **Geist Mono** for numbers, data, metadata labels and axes. Still **no JetBrains, no Inter**.
  - **No pills:** every chip, tag, button, input and panel is square. One accent: muted **GME gold** (`--accent`). Green / red only for real up / down movement.
  - **Status dot:** one static round dot in the "Data current / Data stale" status (header + hero). Nothing blinks or glows anywhere.
- **Information architecture** (hash routing; old hashes `#wallets #bubbles #insiders #watchlist #valuation #flows` redirect):
  - **Overview:** hero (status line `ETHEREUM MAINNET · DAILY INDEX · LAST INDEXED … · ● DATA CURRENT`, title, contract + copy, a "live index vs research snapshot" block) → 8 executive metrics (4 on phones, "All metrics +") → **primary instrument** (price + realized price / DEX net flow / cluster holdings on one time axis, plus a computed "state of play" for the chosen range) → signals (insider watch, since last run, what changed) → market structure (MVRV, supply in profit, pool).
  - **Holders:** where the supply sits (bar + table, inferred groups hatched), largest holders, largest entities (owner groups from `T.mon`, 7D/30D net), concentration, holders, new wallets, position sizes, HODL waves, cost basis (price vs realized, MVRV, supply in profit, URPD, cohorts).
  - **Transfers:** transfer activity (count / USD value / active addresses, ◆ unusual days = ≥3× the previous 30-day median, a display rule), unusual days, largest movements (90 days), DEX trading, liquidity and exchanges, SOPR / NRPL / liveliness.
  - **Entities** (sub-tabs `#entities/cluster|monitor|map|watchlist`): a **direct evidence vs inferred relationship** legend on every view. Direct = a transfer between the two wallets is on-chain (solid lines); inferred = shared deposit address or same owner group (dashed, tagged "inferred").
    - **Wallet monitor:** change cells are coloured by what the coins did in that window: green in, red only when they left through the DEX or an exchange, amber to wallets outside the group, grey "↔" for moves between wallets of the same owner group (owner asked: own-wallet moves must not read as losses).
    - **Flow map:** draggable bubbles (positions kept per owner+window until ⤢ reset), pan, ctrl+scroll / pinch / +− zoom, hover isolates a bubble's flows, click opens a side panel with its holdings, change and every flow in and out.
  - **Methodology:** research-style write-up (source, reconstruction, pricing, attribution with an evidence column, classifications, limits, freshness) + "Read the full study →".
  - **Wallet drawer:** every address opens it (copy, Etherscan, Zerion, stats, balance + price chart, activity).
- **Data:** `scripts/terminal.py` runs daily, after `watch.py`, and reads each group's members from `watch_state.json`. It writes:
  - **`data/terminal.json`:**
    - daily series since launch: price, the engine's rp/MVRV/sip/SOPR/holders/top10/top100/whale share/NRPL/liveliness/age bands/$-wealth bands/exchange balances, plus DEX buy/sell $ and counts, new wallets, pool GME, focus and cluster balances, and cluster flows by type;
    - the insider status;
    - 180-day group histories;
    - the cluster graph and members;
    - the top 50 holders and live pool reserves;
    - daily `tx` (transfer count), `txVol` (GME, billions), `txUsd`, `active` (distinct non-infrastructure addresses);
    - **`index`**: `indexedAt`, `lastTransfer`, `transfers`, `firstTransfer`, `held` (GME in wallets), `burned`, `tx24h/168h/720h`, `active24h/168h/720h`;
    - **`moves`**: the 60 largest single transfers of the last 90 days (skipping plumbing between two infrastructure addresses), with labels (DEX / Exchange / Liquidity / Burn / Mint / Token contract) and group names for each end;
    - **`mon`**, the monitor and bubble map data:
      - `A` = addresses;
      - `M[i]` = [balance B, owner index, monitored flag, first seen, last active] for tracked wallets;
      - `owners` = focus cluster → watched groups → unflagged linked groups from `entities_all.json` that hold a monitored wallet;
      - `e` = every transfer touching a tracked wallet in the last 90 days, aggregated per hour as [hour, from, to, GME in billions]. A counterparty that isn't tracked is a category: D = DEX, C = exchange, L = liquidity, B = burn, T = token contract, or its address.
      
      The page computes every window, status and map from `e`.
  - **`data/wallets.json`:** per-wallet daily balance + transfer events (merged per day / type / counterparty) for every watched wallet, cluster member and top holder.
  
  `scripts/build-site.mjs` puts terminal.json into `dist/site.json` as `T`, next to alerts, accumulators, holding wallets and float, and copies wallets.json alongside.
- **Insider status rules** (focus wallet's cluster, in `terminal.py`):
  - DISTRIBUTING: sent ≥0.05% of supply to exchanges in 30 days.
  - SELLING: sold more than it bought on the DEX and shrank.
  - ACCUMULATING: grew by more than 0.05% of supply.
  - HOLDING: otherwise.
  
  **Tripwire:** any exchange deposit in 7 days, or the focus wallet selling on the DEX in 30 days. A transfer to the GME token contract itself is NOT a DEX sale; it was the only "sale" in the focus wallet's history.
- **Chart rules:**
  - one y-axis per chart;
  - price and realized price share a log axis (same unit);
  - stacked bars split up (bought, withdrawn) and down (sent to exchanges, sold);
  - more than 200 days of bars become weekly totals, and daily-average lines are dropped at that point;
  - % charts are capped at 100;
  - colours are passed as CSS variable names, so the theme toggle repaints.
- `vercel.json`: no framework, build command `node scripts/build-site.mjs`, output `dist`. Every push to `main`, including the daily data commit, redeploys. **Production URL: https://gme-terminal.vercel.app** (Vercel project `gme-terminal`, team cianfru's projects, repo `cianfru/GME`). Deployment protection is standard: the production domain is public, preview URLs require Vercel login.
- **Password is optional (owner: "keep it simple, a side project").** `middleware.js` adds HTTP Basic auth only when the `SITE_PASSWORD` env var is set. Without it the site is open, and `noindex` keeps it out of search. Tests: `npm test`.
- **Freshness:** age = now − `T.index.indexedAt`. After 12 hours (runs every 4 h) the status turns to "Data stale" (gold) in the header and hero. The last day of every daily chart is partial (tooltips say so).
- **Header:** the token logo (`site/logo.png`, CoinGecko's "GME (Ethereum)" image, also the favicon) + "GME on Ethereum", the five-section nav (thin gold underline on the active one), the data status and a text LIGHT/DARK toggle.
- **"Still holding"** (a buy-and-hide wallet) means it kept ≥80% of what it received AND sold or deposited ≤20% of it.
  - Since 2026-10-30, `vaults90.py` keeps ONLY those in `vaults90.json`, so they alone feed the accumulator tags and the watch groups. The relays that bought and then sold or passed the coins on go to `vaults90_relays.json` and are just counted on the page.
  - Owner: "bought and sold is not accumulation." A trader that refills, like `0x859f…d9d1` which sold 3.3B, is not a hider.

## 4. Linking rules (what makes two wallets one owner)

Each rule below links two wallets:
- **seed:** the first GME a wallet ever received (at least $2k worth) came from the other wallet.
- **drain:** a wallet sent at least 90% of its balance (at least $2k worth) to the other.
- **shared exchange deposit address:** both used the same deposit address. Only counts when 2 to 10 wallets share it, and the address forwards at least 95% to an exchange.
- **ethfund:** the focus wallet sent at least 0.1 ETH to the other wallet.
- **gas link:** one sent the other at least 0.001 ETH, and **both** wallets are already on the watchlist.
- **first ETH / gas top-up (ETH side, since 2026-11-08):** one sent the other its very first ETH, or topped it up with ≤0.05 ETH with no GME coming back (§8). `ethside.py` writes them to `data/eth_links.json`; the next run's `cluster_all.py` links through them like a seed or drain, and `entities.py` attaches an unowned wallet to the group of a member it is linked to this way (any date, same caps). Weak and inferred ETH evidence (larger ETH transfers, paid purchases, shared first funder) never groups wallets.

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
- **Wallet monitor, first read (7 days to 2026-10-30):**
  - 22 monitored wallets accumulating (+8.76B) vs 4 reducing (−1.60B); the rest dormant.
  - The #2 holder `0x8d10…a8c8` (14.2B, 3.4%, not linked to anyone) has been selling on the DEX: −1.8B in 90 days, −740M in 7 days.
  - Linked group `0xd657…2f48` bought and sold back.
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

## 7. Entities, crowd and the 4-hour scan (built 2026-11-05)

- **Schedule:** `daily.yml` runs **full** at 06:23 UTC and **light every 4 hours** (`47 */4 * * *`). Light skips the external lookups (`refresh_focus.py`, `funders_ethplorer.py`, the second `stealth.py`) and does not commit `wallets.json` (git size). A run takes about 1–2 minutes. Stale = 12 h.
- **`groups.py`:** the watched groups, built once for `watch.py` and `entities.py`. `with_attached()` adds the registry's joined wallets, so a move into them is internal.
- **`entities.py` → `data/entities.json`:** every group of linked wallets is an entity with a **stable id**, matched run to run by shared members.
  - Sources in priority order: focus cluster → Coinbase group → watched groups → unflagged `entities_all.json` groups holding ≥0.05% of supply.
  - **Follow the coins** (last 90 days, no hop limit): seed or drain with a member, ≥$2k. Never through infrastructure, contracts, deposit-like addresses or hubs (>40 seeds). Linked groups are capped at 60; at most 25 joins per entity per run. **Joins are sticky.** Wallets that got ≥$2k in 30 days with no rule firing are **provisional**: shown, never counted.
  - Per entity: holdings, a 90-day series (today's members), flows by channel over 1/7/30/90 days (`channels` names the columns), status, FIFO cost basis, evidence strength for the focus cluster, forming flags, `edges` between entities and categories, `alerts` (tripwires since the last run) and the last 300 `events`.
  - `terminal.py` builds the monitor's owners from the registry (`owners[k].id`; `M[i][5]` = provisional owner).
- **Shared deposit evidence (owner asked how it is known):** a deposit address is inferred from behaviour: it forwarded ≥95% to a labelled exchange and received from 2–10 wallets. Two wallets paying into it funded one exchange account. That is evidence of one owner, not proof: a friend's account, an OTC settlement or a personal relay look the same. Focus cluster: **58.2B of 65.0B reaches the focus wallet through direct transfers only; 6.8B depends on a shared deposit somewhere on the path.**
- **`crowd.py` → `data/crowd.json`:** owner-level (entity = one owner) market flows, aligned with `terminal.json` days:
  - buyers new / returning / adding;
  - sellers sold-out / kept-a-position and profit / loss;
  - realized P/L;
  - distinct owner counts per window (`win`);
  - arrival-quarter cohorts;
  - smart money: realized ≥$5k and ≥100% on cost, a hindsight pick.
  Cross-checked: crowd buys = DEX buys + exchange withdrawals.
- **`notify.py`:** high watch alerts plus high/medium entity tripwires go into a comment on issue "GME terminal alerts" (#1). Repository variable `ALERT_ISSUE=off` stops it.
- **`data/engine/urpd-history.json`** (the engine's weekly cost-basis distribution) is now committed for the Crowd page heatmap.
- **P&L over time (owner, 2026-11-08: "a PnL chart for each cluster/wallet, and buys and sells on the GME chart").** `scripts/pnl.py` `Book` = one FIFO method for groups and wallets: a DEX buy costs the exact execution price, any other inflow the day's close; a SALE = GME to the DEX or to an exchange (deposit treated as a sale) and realizes; any other outflow (other wallets, liquidity, burn, token contract) leaves AT COST, no P/L. Output: `track` = change-points `[day, holdB, costUsd, realizedUsd, boughtUsd, soldUsd]` (day counted from the first transfer) and `marks` = `[day, b|s|ci|co, GME B, $]` per day and kind. `entities.py` uses it for the card cost basis (so card and chart agree; since 2026-11-08 transfers out no longer realize) and writes **`data/pnl.json`** (all groups, ~290 KB, fetched only when a chart opens); `terminal.py` adds `pnl` + `marks` to each wallet in `wallets.json` (full runs only). Site: `behaviourChart()` = price (log) with the trades as dots sized by $ (filled = DEX at the day's average execution price, ring = exchange deposit/withdrawal at the day's close) · holdings · P&L $ (total, realized, unrealized = holdings × close − cost of held), with All / 1Y / 90D. Opened from "P&L chart →" on every group card and the flow-map side panel (a group drawer: summary, chart, largest trades, wallets), inline on the fbb4 tab, and in every wallet drawer (with a button to its group's chart).
- **Site additions:**
  - **Crowd** page (`#crowd`): reading, valuation composite (client-side, expanding-window ranks, weights 25/25/30/20), buyers/sellers by type, profit/loss sales, cohorts, smart money, cost basis over time, pool and overhang calculator.
  - **Entities** opens on entity cards.
  - The flow map opens at entity level and drills into one owner's wallets.

## 8. The ETH side (BigQuery + public nodes, built 2026-11-07)
- **Key:** repository secret `GCP_SA_KEY` = a JSON key of the SPX service account (project `goog-fltx`; SPX keeps its own older key, both valid; SPX no longer uses BigQuery). Free tier 1 TB scanned per month.
- **`bigquery.yml` (manual, run rarely):** `bq_wallets.py` builds the 4,396 study wallets (entity members, provisional, peak ≥0.05% of supply, holders ≥0.01%, buyers ≥$500 in 180 d) → `bq load` (free) into `gme_study.wallets` → `bq_run.py` (dry run first, then capped). Default queries, measured: **`eth_flows` 218.6 GB** (top-level ETH to/from study wallets since 2024-04-01, per pair, with the sender's lowest nonce: nonce 0 = wallet created in the window) and **`token_footprint` 200.0 GB** (every ERC-20 they sent/received in the last 12 months, counts only). First run 2026-11-07: 147,133 + 117,144 rows committed in `data/bq/`. **Not run:** `first_funder.sql` (813 GB) and `tx_signers.sql` (241 GB).
- **`signers_rpc.py` (each scheduled run, incremental):** who signed every DEX purchase into a study wallet, via batched `eth_getTransactionByHash` on public nodes (57,399 purchases the first time, ~45 min) → `data/bq/signers.csv` (only signer ≠ recipient) + `signers_state.json`.
- **`ethside.py` → `data/ethside.json` + `data/eth_links.json` (each scheduled run):** evidence grades — **strong/direct (they group wallets, §4):** `ethseed` (A sent B its first ETH), `gas` (≤0.05 ETH top-up); **weak:** `eth` (>0.05 ETH, could be a payment) and `paid` (A signed a swap whose GME went straight from a GME pool to B: 16,625 of 57,399 study-wallet purchases are signed by another wallet, 2,486 pool-direct → 144 pairs). **Paid was downgraded on 2026-11-08 after checking it:** the signers are mostly trading-bot executors serving many buyers, many-to-many (one buyer's purchases signed by up to 17 executors, one executor signing for 15 buyers; 120 of 144 pairs deliver to a wallet other signers also bought for). Grouping on them merged strangers: a 16-wallet group around `0x9d32…` and `0x9ae6…` was nothing but executors. **inferred:** `funder` (same private first funder, 2–8 wallets). **Guards:** exchange labels (`eth_labels.csv` + exclude cex), any sender with nonce >50,000, any studied wallet that moved ≥20,000 ETH, any wallet that sent ETH to >12 / received from >8 studied wallets **outside its own entity** (focus wallet's own funding excepted) = SERVICE, never links; ETH one way + GME the other way between the same pair = **OTC-like, not a link** (454 pairs); a signer buying for >10 wallets = relayer. Nothing merges entities: links are candidates on the site (Entities → ETH side).
- **First findings (2026-11-07):**
  - **The ETH trail mostly confirms the existing groups:** 703 strong links → only 2 merges between groups (both small linked groups), 36 wallets holding 14.1B (3.4%) join existing groups (largest `0x8bd6…` 8.49B → linked group `0x4098…`; 6 wallets / 1.83B → focus cluster, e.g. `0x58df…5596` 1.44B by a gas top-up), and 558 links among wallets in no group.
  - **First ETH of the 1,364 wallets created since April 2024:** 487 came from exchanges (Binance 268, Coinbase 92, Bybit 30, Crypto.com 21, MEXC 21…), 411 from private wallets, 173 from another studied wallet and 293 from services.
  - **"Linked group 0xf819…73aa" holds exchange or market-maker wallets** (6 wallets, up to 30M ETH moved, nonce 170k). Its card is flagged. **Verify on Etherscan before adding them to the exclude list.**
  - **Other tokens traded by the same owners:** BOOE (215 owners, 20 groups), pepecoin (165), ASTEROID, Yee… This matches the SPX/pepecoin finding that one crowd trades GME, BOOE and pepecoin. `0xcf2c0423…` (the pepecoin terminal's "one insider still buying") holds 3.05B GME.
  - **Leads:** `0x546b…` (2.28B) received 8.76 ETH from focus member `0x884f…` (June 2024, weak link). The #2 holder `0x8d10…` has a single gas link, to an empty wallet.
- **Strong ETH links group wallets (owner approved 2026-11-08).** First run on real data: 557 strong links (136 first-ETH, 421 gas). Trusted linked groups (unflagged, ≥0.05% of supply) went from 62 holding 96.2B to 76 holding ~119B; existing groups grew (e.g. `0x8bd6…c6a2` 8.49B joined Linked group 847d by gas top-ups), two pairs of small linked groups merged, and new 2–5-wallet groups appeared (largest: Linked group 3146 = `0xcf2c…3146`, the pepecoin "insider still buying", 3.12B, joined to a second wallet by a gas top-up). 5 wallets holding 1.83B joined fbb4 by gas top-ups (largest `0x58df…5596` 1.44B). The flagged mega-group (fbb4's looser web, incl. the #2 holder `0x8d10…a8c8`) grew from 158 to 180 wallets and stays untrusted. Links between two existing groups are not merged (each keeps the wallets it was built from) and stay listed on the ETH side page.

## 9. Still open
- Track whether the accumulators' holding wallets ever send to an exchange (exit tripwire); the entity tripwires now cover first deposits for every entity.
- Trace accumulators' ETH funding one or two hops back.
- Per-chart "as of" dates; tests for the Python builders.
