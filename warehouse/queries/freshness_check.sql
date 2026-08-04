-- Fails the pipeline if the newest observation per asset is older than
-- the given staleness threshold. Parameterize :max_age_minutes at call time.
SELECT
    asset,
    MAX(observed_at) AS latest_observed_at
FROM raw_prices
GROUP BY asset
HAVING MAX(observed_at) < datetime('now', '-' || :max_age_minutes || ' minutes');
