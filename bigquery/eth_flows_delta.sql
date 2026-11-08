-- The weekly top-up of eth_flows.sql: the same rows, but only for transactions AFTER the newest one already in
-- data/bq/eth_flows.csv ({SINCE}, filled in by bq_run.py from `scripts/bq_flows.py cutoff`). The literal timestamp
-- keeps BigQuery to the new day partitions, so this scans a few GB instead of the whole window.
-- bq_flows.py merge folds the result into eth_flows.csv (counts and ETH added, first/last/lowest nonce kept).
WITH w AS (SELECT DISTINCT LOWER(a) AS a FROM `{P}.{DS}.wallets`)
SELECT from_address AS f, to_address AS t, COUNT(*) AS n, CAST(SUM(value) / 1e18 AS FLOAT64) AS eth,
       MIN(block_timestamp) AS first, MAX(block_timestamp) AS last, MIN(nonce) AS min_nonce
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE block_timestamp > TIMESTAMP '{SINCE}' AND value > 0 AND receipt_status = 1
  AND (from_address IN (SELECT a FROM w) OR to_address IN (SELECT a FROM w))
GROUP BY f, t
