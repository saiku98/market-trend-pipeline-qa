import sqlite3
from pathlib import Path

import pytest

from spark_jobs.trend_forecast import compute_trends_pandas, write_trends
from warehouse.loader import apply_schema


@pytest.fixture
def db_with_prices(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    apply_schema(db_path)
    prices = [
        ("bitcoin", 100.0, "2026-08-04T00:00:00"),
        ("bitcoin", 101.0, "2026-08-04T00:01:00"),
        ("bitcoin", 102.0, "2026-08-04T00:02:00"),
        ("bitcoin", 103.0, "2026-08-04T00:03:00"),
        ("bitcoin", 110.0, "2026-08-04T00:04:00"),
    ]
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO raw_prices (asset, price_usd, observed_at) VALUES (?, ?, ?)",
            prices,
        )
    return db_path


def test_compute_trends_requires_full_window(db_with_prices):
    rows = compute_trends_pandas(db_with_prices, window=5)
    assert len(rows) == 1  # exactly one full window of 5 ticks
    assert rows[0].asset == "bitcoin"


def test_compute_trends_labels_upward_momentum(db_with_prices):
    rows = compute_trends_pandas(db_with_prices, window=5)
    assert rows[0].trend_label == "up"
    assert rows[0].momentum > 0


def test_compute_trends_too_few_rows_returns_empty(db_with_prices):
    rows = compute_trends_pandas(db_with_prices, window=10)
    assert rows == []


def test_write_trends_persists_rows(db_with_prices):
    rows = compute_trends_pandas(db_with_prices, window=5)
    n = write_trends(db_with_prices, rows)
    assert n == 1
    conn = sqlite3.connect(db_with_prices)
    count = conn.execute("SELECT COUNT(*) FROM trend_metrics").fetchone()[0]
    assert count == 1
