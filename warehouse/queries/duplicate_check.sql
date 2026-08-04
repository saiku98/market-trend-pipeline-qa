-- Duplicate (asset, observed_at) pairs indicate a retry bug in the ingestor
-- writing the same observation twice.
SELECT asset, observed_at, COUNT(*) AS n
FROM raw_prices
GROUP BY asset, observed_at
HAVING COUNT(*) > 1;
