-- The first ETH each study wallet ever received (full history: a wallet's first funder can predate GME).
WITH w AS (SELECT DISTINCT LOWER(a) AS a FROM `{P}.{DS}.wallets`)
SELECT to_address AS a, from_address AS funder, CAST(value / 1e18 AS FLOAT64) AS eth, block_timestamp AS ts, `hash` AS tx
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE value > 0 AND receipt_status = 1 AND to_address IN (SELECT a FROM w)
QUALIFY ROW_NUMBER() OVER (PARTITION BY to_address ORDER BY block_timestamp, transaction_index) = 1
