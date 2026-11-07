-- Every ERC-20 the study wallets sent or received since GME launched (2024-05-13), per wallet and token: transfer
-- counts, raw amounts in and out, first and last activity, with the token's symbol, name and decimals.
WITH w AS (SELECT DISTINCT LOWER(a) AS a FROM `{P}.{DS}.wallets`),
k AS (SELECT address, ANY_VALUE(symbol) AS symbol, ANY_VALUE(name) AS name, ANY_VALUE(SAFE_CAST(decimals AS INT64)) AS dec
      FROM `bigquery-public-data.crypto_ethereum.tokens` GROUP BY address),
tt AS (SELECT token_address, from_address, to_address, SAFE_CAST(value AS BIGNUMERIC) AS v, block_timestamp
       FROM `bigquery-public-data.crypto_ethereum.token_transfers`
       WHERE block_timestamp >= TIMESTAMP '2024-05-13' AND token_address != '0xc56c7a0eaa804f854b536a5f3d5f49d2ec4b12b8'),
legs AS (SELECT w.a, tt.token_address AS token, 1 AS dir, tt.v, tt.block_timestamp FROM tt JOIN w ON tt.to_address = w.a
         UNION ALL
         SELECT w.a, tt.token_address, -1, tt.v, tt.block_timestamp FROM tt JOIN w ON tt.from_address = w.a)
SELECT legs.a, legs.token, k.symbol, k.name, k.dec,
       COUNTIF(dir = 1) AS nin, COUNTIF(dir = -1) AS nout,
       CAST(SUM(IF(dir = 1, v, 0)) AS STRING) AS rin, CAST(SUM(IF(dir = -1, v, 0)) AS STRING) AS rout,
       MIN(block_timestamp) AS first, MAX(block_timestamp) AS last
FROM legs LEFT JOIN k ON k.address = legs.token
GROUP BY legs.a, legs.token, k.symbol, k.name, k.dec
