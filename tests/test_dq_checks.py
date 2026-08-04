import sqlite3
from pathlib import Path

import pytest

from validation.python.checks import (
    check_freshness,
    check_no_duplicates,
    check_no_nulls_or_bad_ranges,
    check_trend_label_values_valid,
    check_trend_metrics_not_empty,
    run_all_checks,
)
from warehouse.loader import apply_schema


@pytest.fixture
def clean_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "clean.db"
    apply_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO raw_prices (asset, price_usd, observed_at) VALUES (?, ?, datetime('now'))",
            ("bitcoin", 50000.0),
        )
        conn.execute(
            "INSERT INTO trend_metrics "
            "(asset, window_end, window_size, moving_avg_usd, volatility, momentum, trend_label) "
            "VALUES ('bitcoin', datetime('now'), 5, 50000.0, 10.0, 0.5, 'up')"
        )
    return db_path


def test_no_nulls_check_passes_on_clean_data(clean_db):
    assert check_no_nulls_or_bad_ranges(clean_db).passed


def test_no_nulls_check_fails_on_bad_price(tmp_path):
    db_path = tmp_path / "bad.db"
    apply_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO raw_prices (asset, price_usd, observed_at) VALUES ('bitcoin', -5, datetime('now'))"
        )
    result = check_no_nulls_or_bad_ranges(db_path)
    assert not result.passed
    assert "1 row" in result.details


def test_no_duplicates_check_fails_on_dupe(tmp_path):
    db_path = tmp_path / "dupe.db"
    apply_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO raw_prices (asset, price_usd, observed_at) VALUES ('bitcoin', 100, '2026-08-04T00:00:00')"
        )
        conn.execute(
            "INSERT INTO raw_prices (asset, price_usd, observed_at) VALUES ('bitcoin', 101, '2026-08-04T00:00:00')"
        )
    result = check_no_duplicates(db_path)
    assert not result.passed


def test_freshness_check_fails_when_stale(tmp_path):
    db_path = tmp_path / "stale.db"
    apply_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO raw_prices (asset, price_usd, observed_at) VALUES ('bitcoin', 100, '2020-01-01T00:00:00')"
        )
    result = check_freshness(db_path, max_age_minutes=60)
    assert not result.passed


def test_trend_metrics_not_empty_fails_on_empty_table(tmp_path):
    db_path = tmp_path / "empty.db"
    apply_schema(db_path)
    result = check_trend_metrics_not_empty(db_path)
    assert not result.passed


def test_trend_label_values_valid_flags_bad_label(tmp_path):
    db_path = tmp_path / "badlabel.db"
    apply_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO trend_metrics "
            "(asset, window_end, window_size, moving_avg_usd, volatility, momentum, trend_label) "
            "VALUES ('bitcoin', datetime('now'), 5, 100.0, 1.0, 0.1, 'sideways')"
        )
    result = check_trend_label_values_valid(db_path)
    assert not result.passed


def test_run_all_checks_logs_to_dq_table(clean_db):
    results = run_all_checks(clean_db)
    assert len(results) == 5
    conn = sqlite3.connect(clean_db)
    logged = conn.execute("SELECT COUNT(*) FROM dq_check_results").fetchone()[0]
    assert logged == 5
