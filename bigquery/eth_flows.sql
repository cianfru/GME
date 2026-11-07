-- Native ETH sent in top-level transactions to or from the study wallets since 2024-01-01, one row per sender →
-- receiver pair. The literal date keeps BigQuery to the partitions it needs (a subquery bound would scan everything).
-- Internal ETH (sent by contracts, e.g. some exchange withdrawals) is not in this table; stated on the site.
WITH w AS (SELECT DISTINCT LOWER(a) AS a FROM `{P}.{DS}.wallets`)
SELECT from_address AS f, to_address AS t, COUNT(*) AS n, CAST(SUM(value) / 1e18 AS FLOAT64) AS eth,
       MIN(block_timestamp) AS first, MAX(block_timestamp) AS last
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE block_timestamp >= TIMESTAMP '2024-01-01' AND value > 0 AND receipt_status = 1
  AND (from_address IN (SELECT a FROM w) OR to_address IN (SELECT a FROM w))
GROUP BY f, t
