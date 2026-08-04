import sqlite3
from pathlib import Path

import pytest

from reports.daily_report_generator import generate_report
from warehouse.loader import apply_schema


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "report.db"
    apply_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO trend_metrics "
            "(asset, window_end, window_size, moving_avg_usd, volatility, momentum, trend_label) "
            "VALUES ('bitcoin', '2026-08-04T00:00:00', 5, 50000.0, 120.5, 0.8, 'up')"
        )
        conn.execute(
            "INSERT INTO dq_check_results (check_name, target_table, status, details, run_at) "
            "VALUES ('freshness_check', 'raw_prices', 'pass', 'ok', '2026-08-04T00:00:00')"
        )
    return db_path


def test_report_includes_asset_and_trend_label(populated_db):
    html = generate_report(populated_db)
    assert "bitcoin" in html
    assert "up" in html


def test_report_includes_dq_status(populated_db):
    html = generate_report(populated_db)
    assert "freshness_check" in html
    assert 'class="pass"' in html


def test_report_handles_empty_db(tmp_path):
    db_path = tmp_path / "empty.db"
    apply_schema(db_path)
    html = generate_report(db_path)
    assert "No data available." in html
