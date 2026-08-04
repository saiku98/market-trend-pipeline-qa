-- Warehouse schema for the market trend pipeline.
-- Written to be portable between SQLite (local/dev, used by this repo's
-- scripts and tests) and Postgres (intended production target).

CREATE TABLE IF NOT EXISTS raw_prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,   -- Postgres: use SERIAL / IDENTITY
    asset TEXT NOT NULL,
    price_usd REAL NOT NULL,
    observed_at TEXT NOT NULL               -- ISO-8601 UTC timestamp
);

CREATE INDEX IF NOT EXISTS idx_raw_prices_asset_time
    ON raw_prices (asset, observed_at);

-- Rolling trend indicators computed by the Spark job (spark_jobs/trend_forecast.py)
CREATE TABLE IF NOT EXISTS trend_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset TEXT NOT NULL,
    window_end TEXT NOT NULL,       -- end of the rolling window, ISO-8601 UTC
    window_size INTEGER NOT NULL,   -- number of observations in the window
    moving_avg_usd REAL NOT NULL,
    volatility REAL NOT NULL,       -- stddev of price over the window
    momentum REAL NOT NULL,         -- pct change vs. previous window
    trend_label TEXT NOT NULL       -- 'up' | 'down' | 'flat'
);

CREATE INDEX IF NOT EXISTS idx_trend_metrics_asset_time
    ON trend_metrics (asset, window_end);

-- Log of every data-quality check run, written by validation/python/checks.py
-- and read by the Java validation module for CI gating.
CREATE TABLE IF NOT EXISTS dq_check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    check_name TEXT NOT NULL,
    target_table TEXT NOT NULL,
    status TEXT NOT NULL,           -- 'pass' | 'fail'
    details TEXT,
    run_at TEXT NOT NULL
);
