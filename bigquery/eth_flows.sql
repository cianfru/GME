-- Native ETH sent in top-level transactions to or from the study wallets since 2024-04-01, one row per sender →
-- receiver pair, with the sender's lowest nonce in the window (nonce 0 = the wallet's first transaction ever, so it
-- was created inside the window and its first funder is in this data). The literal date keeps BigQuery to the
-- partitions it needs. Internal ETH (sent by contracts, e.g. some exchange withdrawals) is not in this table.
WITH w AS (SELECT DISTINCT LOWER(a) AS a FROM `{P}.{DS}.wallets`)
SELECT from_address AS f, to_address AS t, COUNT(*) AS n, CAST(SUM(value) / 1e18 AS FLOAT64) AS eth,
       MIN(block_timestamp) AS first, MAX(block_timestamp) AS last, MIN(nonce) AS min_nonce
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE block_timestamp >= TIMESTAMP '2024-04-01' AND value > 0 AND receipt_status = 1
  AND (from_address IN (SELECT a FROM w) OR to_address IN (SELECT a FROM w))
GROUP BY f, t
