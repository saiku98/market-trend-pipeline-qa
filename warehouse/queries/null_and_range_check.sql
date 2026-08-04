-- Rows that violate basic sanity constraints: null/blank asset, non-positive
-- price, or malformed timestamp. Any rows returned here should fail CI.
SELECT *
FROM raw_prices
WHERE asset IS NULL
   OR TRIM(asset) = ''
   OR price_usd IS NULL
   OR price_usd <= 0
   OR observed_at IS NULL;
