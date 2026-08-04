"""Data-quality validation framework for the market trend pipeline.

Each check is a small, independently runnable function that:
  * queries the warehouse (SQLite locally, same SQL works on Postgres),
  * returns a `CheckResult`,
  * and is logged to `dq_check_results` so failures are auditable over time.

This is intentionally dependency-light (no Great Expectations / dbt) so it
is easy to read end-to-end and easy to run in CI without extra services.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

QUERIES_DIR = Path(__file__).resolve().parents[2] / "warehouse" / "queries"


@dataclass(frozen=True)
class CheckResult:
    name: str
    target_table: str
    passed: bool
    details: str = ""


def _run_query(db_path: Path, sql: str, params: dict | None = None) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(sql, params or {})
        return cur.fetchall()


def check_no_nulls_or_bad_ranges(db_path: Path) -> CheckResult:
    sql = (QUERIES_DIR / "null_and_range_check.sql").read_text()
    bad_rows = _run_query(db_path, sql)
    return CheckResult(
        name="null_and_range_check",
        target_table="raw_prices",
        passed=len(bad_rows) == 0,
        details=f"{len(bad_rows)} row(s) with null/invalid values" if bad_rows else "ok",
    )


def check_no_duplicates(db_path: Path) -> CheckResult:
    sql = (QUERIES_DIR / "duplicate_check.sql").read_text()
    dupes = _run_query(db_path, sql)
    return CheckResult(
        name="duplicate_check",
        target_table="raw_prices",
        passed=len(dupes) == 0,
        details=f"{len(dupes)} duplicate (asset, observed_at) pair(s)" if dupes else "ok",
    )


def check_freshness(db_path: Path, max_age_minutes: int = 60) -> CheckResult:
    sql = (QUERIES_DIR / "freshness_check.sql").read_text()
    stale = _run_query(db_path, sql, {"max_age_minutes": max_age_minutes})
    return CheckResult(
        name="freshness_check",
        target_table="raw_prices",
        passed=len(stale) == 0,
        details=f"{len(stale)} asset(s) with no data in the last {max_age_minutes}m" if stale else "ok",
    )


def check_trend_metrics_not_empty(db_path: Path) -> CheckResult:
    rows = _run_query(db_path, "SELECT COUNT(*) FROM trend_metrics")
    count = rows[0][0]
    return CheckResult(
        name="trend_metrics_not_empty",
        target_table="trend_metrics",
        passed=count > 0,
        details=f"{count} row(s) in trend_metrics",
    )


def check_trend_label_values_valid(db_path: Path) -> CheckResult:
    rows = _run_query(
        db_path,
        "SELECT COUNT(*) FROM trend_metrics WHERE trend_label NOT IN ('up','down','flat')",
    )
    bad_count = rows[0][0]
    return CheckResult(
        name="trend_label_values_valid",
        target_table="trend_metrics",
        passed=bad_count == 0,
        details=f"{bad_count} row(s) with an unexpected trend_label" if bad_count else "ok",
    )


ALL_CHECKS = (
    check_no_nulls_or_bad_ranges,
    check_no_duplicates,
    check_freshness,
    check_trend_metrics_not_empty,
    check_trend_label_values_valid,
)


def run_all_checks(db_path: Path, *, freshness_minutes: int = 60) -> list[CheckResult]:
    results = []
    for check_fn in ALL_CHECKS:
        if check_fn is check_freshness:
            results.append(check_fn(db_path, max_age_minutes=freshness_minutes))
        else:
            results.append(check_fn(db_path))
    _log_results(db_path, results)
    return results


def _log_results(db_path: Path, results: list[CheckResult]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO dq_check_results (check_name, target_table, status, details, run_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (r.name, r.target_table, "pass" if r.passed else "fail", r.details, now)
                for r in results
            ],
        )


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="data/market_data.db")
    parser.add_argument("--freshness-minutes", type=int, default=60)
    args = parser.parse_args()

    results = run_all_checks(Path(args.db_path), freshness_minutes=args.freshness_minutes)
    failed = [r for r in results if not r.passed]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"[{status}] {r.name} ({r.target_table}): {r.details}")

    if failed:
        print(f"\n{len(failed)} check(s) failed.")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
