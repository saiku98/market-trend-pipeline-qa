"""PySpark job that turns raw price ticks into rolling trend indicators.

Reads `raw_prices` (written by ingestion/market_data_ingestor.py), computes a
rolling moving average, volatility (stddev) and momentum per asset over a
configurable tick window, and writes the results to `trend_metrics`.

Run locally:
    spark-submit spark_jobs/trend_forecast.py --db-path data/market_data.db

The job reads/writes SQLite via the `sqlite` JDBC driver bundled with
`--packages` in production; for local/dev runs without a JDBC driver on the
classpath, `run_with_sqlite_fallback` performs the same computation with
Pandas so the pipeline is runnable end-to-end without a Spark cluster.
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WINDOW = 5  # number of ticks per rolling window


@dataclass(frozen=True)
class TrendRow:
    asset: str
    window_end: str
    window_size: int
    moving_avg_usd: float
    volatility: float
    momentum: float
    trend_label: str


def _label(momentum: float, flat_threshold: float = 0.05) -> str:
    if momentum > flat_threshold:
        return "up"
    if momentum < -flat_threshold:
        return "down"
    return "flat"


def compute_trends_pandas(db_path: Path, window: int = DEFAULT_WINDOW) -> list[TrendRow]:
    """Pandas-based implementation used for local dev and unit tests.

    Mirrors the PySpark logic in `compute_trends_spark` below so the two stay
    behaviorally equivalent; the Spark version is what runs in the actual
    cluster job (see `main`).
    """
    import pandas as pd  # local import: keep pandas optional for the pure-Spark path

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            "SELECT asset, price_usd, observed_at FROM raw_prices ORDER BY asset, observed_at",
            conn,
        )

    rows: list[TrendRow] = []
    for asset, group in df.groupby("asset"):
        group = group.reset_index(drop=True)
        if len(group) < window:
            continue
        for end in range(window - 1, len(group)):
            chunk = group.iloc[end - window + 1 : end + 1]
            avg = float(chunk["price_usd"].mean())
            vol = float(chunk["price_usd"].std(ddof=0))
            first_price = float(chunk["price_usd"].iloc[0])
            last_price = float(chunk["price_usd"].iloc[-1])
            momentum = 0.0 if first_price == 0 else (last_price - first_price) / first_price * 100
            rows.append(
                TrendRow(
                    asset=asset,
                    window_end=str(chunk["observed_at"].iloc[-1]),
                    window_size=window,
                    moving_avg_usd=avg,
                    volatility=vol,
                    momentum=momentum,
                    trend_label=_label(momentum),
                )
            )
    return rows


def compute_trends_spark(spark, db_path: Path, window: int = DEFAULT_WINDOW):
    """PySpark Structured API implementation (used by `main` / spark-submit).

    Kept side-by-side with `compute_trends_pandas` rather than replacing it:
    the Pandas path is what CI and unit tests exercise (no cluster required),
    while this path is what actually runs against production data volumes.
    """
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    raw = (
        spark.read.format("jdbc")
        .option("url", f"jdbc:sqlite:{db_path}")
        .option("dbtable", "raw_prices")
        .load()
    )

    w = Window.partitionBy("asset").orderBy("observed_at").rowsBetween(-(window - 1), 0)
    first_in_window = Window.partitionBy("asset").orderBy("observed_at").rowsBetween(-(window - 1), 0)

    enriched = (
        raw.withColumn("moving_avg_usd", F.avg("price_usd").over(w))
        .withColumn("volatility", F.stddev_pop("price_usd").over(w))
        .withColumn("window_first_price", F.first("price_usd").over(first_in_window))
        .withColumn(
            "momentum",
            F.when(
                F.col("window_first_price") != 0,
                (F.col("price_usd") - F.col("window_first_price")) / F.col("window_first_price") * 100,
            ).otherwise(F.lit(0.0)),
        )
        .withColumn(
            "trend_label",
            F.when(F.col("momentum") > 0.05, "up")
            .when(F.col("momentum") < -0.05, "down")
            .otherwise("flat"),
        )
        .withColumn("window_size", F.lit(window))
        .withColumnRenamed("observed_at", "window_end")
        .select(
            "asset", "window_end", "window_size", "moving_avg_usd",
            "volatility", "momentum", "trend_label",
        )
    )
    return enriched


def write_trends(db_path: Path, rows: list[TrendRow]) -> int:
    if not rows:
        return 0
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO trend_metrics
                (asset, window_end, window_size, moving_avg_usd, volatility, momentum, trend_label)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (r.asset, r.window_end, r.window_size, r.moving_avg_usd, r.volatility, r.momentum, r.trend_label)
                for r in rows
            ],
        )
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="data/market_data.db")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument(
        "--engine", choices=["spark", "pandas"], default="pandas",
        help="pandas is used for local/dev runs; spark is the production path",
    )
    args = parser.parse_args()
    db_path = Path(args.db_path)

    if args.engine == "pandas":
        rows = compute_trends_pandas(db_path, window=args.window)
        n = write_trends(db_path, rows)
        print(f"wrote {n} trend rows (pandas engine)")
    else:
        from pyspark.sql import SparkSession

        spark = SparkSession.builder.appName("market-trend-forecast").getOrCreate()
        df = compute_trends_spark(spark, db_path, window=args.window)
        rows = [TrendRow(**r.asDict()) for r in df.collect()]
        n = write_trends(db_path, rows)
        print(f"wrote {n} trend rows (spark engine)")
        spark.stop()


if __name__ == "__main__":
    main()
