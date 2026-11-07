-- NOT RUN BY DEFAULT: scans ~241 GB. signers_rpc.py gets the same answer free from public nodes (eth_getTransactionByHash).
-- Who signed each GME purchase (the wallet that paid gas and sent the ETH), for every DEX buy in the archive.
-- A purchase signed by one wallet but delivered to another is direct evidence the two are related.
SELECT t.`hash` AS tx, t.from_address AS signer, t.to_address AS target
FROM `bigquery-public-data.crypto_ethereum.transactions` t
JOIN (SELECT DISTINCT LOWER(tx) AS tx FROM `{P}.{DS}.txs`) x ON x.tx = t.`hash`
WHERE t.block_timestamp >= TIMESTAMP '2024-05-13'
