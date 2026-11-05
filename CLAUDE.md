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
- **Freshness:** age = now − `T.index.indexedAt`. After 36 hours the status turns to "Data stale" (gold) in the header and hero. The last day of every daily chart is partial (tooltips say so).
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

## 7. Roadmap (proposed 2026-11-05 after the redesign; waiting for the owner's go and order)

Owner's goals: SPX-level depth on how the crowd moves, a hands-off scan that follows coins into fresh wallets, entity cards that show who is growing or shrinking, own-wallet moves never shown as selling, and a usable bubble map.

**How fresh wallets are handled today (owner asked):** the clusters are rebuilt from the full transfer history on every daily run, so a fresh wallet joins on the next run if a rule fires (its first GME came from a member, ≥$2k; or a member sent it ≥90% of its balance). Gaps:
- up to about a day of lag (cron 06:23 UTC, often hours late); until then the move shows as "→ moved out" (amber), never as selling;
- the focus cluster stops 2 hops from the focus wallet (`cluster.py` tiers 1–2), so a wallet seeded by a tier-2 wallet is not added;
- a partial split (<90%) into a wallet that already held GME, or anything under $2k, does not link;
- the monitor only tracks wallets ≥0.1% of supply plus owner-group wallets.

**1. Entities as first-class objects**
- `entities.py`: a persistent registry with stable IDs, daily membership and size history, and events (wallet joined, split, consolidation, DEX buy/sell, exchange deposit). Flag >60 wallets as before.
- Follow the coins: every run, check each entity's outflows to fresh wallets. Attach when a rule fires, with no hop limit from existing members (hub and size guards stay). Otherwise show the wallet as "provisional · received X from entity" (inferred, dashed), visible at once but not counted as owned.
- Entity cards (Entities, default view): one card per entity with wallets, holdings and % supply, a 90-day sparkline, and 1D/7D/30D change split by channel (DEX buy, exchange in, DEX sell, exchange out, out to wallets outside the group, ↔ internal). Also status, entity cost basis and P/L (FIFO engine per entity), last activity and wallets that joined. A "forming" strip shows new or fast-growing entities.

**2. Crowd behaviour (port from SPX / pepecoin)**
- Buyer flow: daily net accumulation split into new, reactivated, adding and selling.
- Exit flow: daily exits split into profit and loss.
- Cohort survival as a time series.
- Smart money: per-wallet realized P&L and ROI; are proven winners buying now?
- URPD over time, plus a pool-and-overhang calculator: buy $X → new price, and how much underwater supply sits between today and that price.
- Valuation composite (0–1, weights published).
- A daily plain-language reading: positions, never signals.

**3. Flow map v2:** two levels. An entity map (bubble = entity, arrows = flows between entities, DEX and exchanges, accumulators left and distributors right) opens into its wallets. Adds search/highlight, edge filters (hide internal, DEX/exchanges only), a minimum-flow slider and a day-by-day replay of the window.

**4. Hands-off:**
- A light intraday job every 3–4 h: delta pull, entity outflow check, alerts. The full rebuild stays daily.
- The repo is private, so watch the 2,000 Actions minutes/month: measure run time first.
- Per-entity tripwires: first exchange deposit, first DEX sale, split into fresh wallets.
- An alert channel.
- A freshness audit for every feed.

**5. Quality:** per-chart "as of"; tests for every new builder; a Methods page entry for each new rule.

Older ideas still open:
- Track whether the accumulators' holding wallets ever send to an exchange. That is the exit tripwire.
- Trace accumulators' ETH funding one or two hops back, to see whether one source funds several of them.
