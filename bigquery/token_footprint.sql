-- Every ERC-20 the study wallets sent or received in the last 12 months, per wallet and token: transfer counts in and
-- out, first and last activity, with the token's symbol and name. No amounts (they double the bytes scanned); tokens
-- a wallet only ever received are usually spam airdrops and are filtered out locally.
WITH w AS (SELECT DISTINCT LOWER(a) AS a FROM `{P}.{DS}.wallets`),
k AS (SELECT address, ANY_VALUE(symbol) AS symbol, ANY_VALUE(name) AS name FROM `bigquery-public-data.crypto_ethereum.tokens` GROUP BY address),
tt AS (SELECT token_address, from_address, to_address, block_timestamp
       FROM `bigquery-public-data.crypto_ethereum.token_transfers`
       WHERE block_timestamp >= TIMESTAMP '2025-11-01' AND token_address != '0xc56c7a0eaa804f854b536a5f3d5f49d2ec4b12b8'),
legs AS (SELECT w.a, tt.token_address AS token, 1 AS dir, tt.block_timestamp FROM tt JOIN w ON tt.to_address = w.a
         UNION ALL
         SELECT w.a, tt.token_address, -1, tt.block_timestamp FROM tt JOIN w ON tt.from_address = w.a)
SELECT legs.a, legs.token, k.symbol, k.name, COUNTIF(dir = 1) AS nin, COUNTIF(dir = -1) AS nout, MIN(block_timestamp) AS first, MAX(block_timestamp) AS last
FROM legs LEFT JOIN k ON k.address = legs.token
GROUP BY legs.a, legs.token, k.symbol, k.name
