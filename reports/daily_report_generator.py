"""Generates a daily HTML summary report of pipeline health and market trends.

Intended to run once a day (e.g. via the `daily-report` job in the CI
workflow, or a cron trigger) and be attached/emailed or archived as a build
artifact. Deliberately dependency-light: stdlib `string.Template` instead of
pulling in a full templating engine.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from string import Template

REPORT_TEMPLATE = Template(
    """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Market Trend Daily Report - $report_date</title>
  <style>
    body { font-family: -apple-system, Arial, sans-serif; margin: 2rem; color: #1a1a1a; }
    h1 { font-size: 1.4rem; }
    table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; }
    th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left; font-size: 0.9rem; }
    th { background: #f4f4f4; }
    .pass { color: #167c3f; font-weight: bold; }
    .fail { color: #c0392b; font-weight: bold; }
  </style>
</head>
<body>
  <h1>Market Trend Pipeline &mdash; Daily Report ($report_date)</h1>

  <h2>Latest trend by asset</h2>
  $trend_table

  <h2>Data-quality checks (most recent run)</h2>
  $dq_table

  <p><em>Generated $generated_at</em></p>
</body>
</html>
"""
)


def _rows_to_html_table(headers: list[str], rows: list[tuple], status_col: int | None = None) -> str:
    if not rows:
        return "<p>No data available.</p>"
    thead = "".join(f"<th>{h}</th>" for h in headers)
    body_rows = []
    for row in rows:
        cells = []
        for i, val in enumerate(row):
            css = ""
            if status_col is not None and i == status_col:
                css = ' class="pass"' if str(val) == "pass" else ' class="fail"'
            cells.append(f"<td{css}>{val}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def generate_report(db_path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        trend_rows = conn.execute(
            """
            SELECT asset, moving_avg_usd, volatility, momentum, trend_label, window_end
            FROM trend_metrics t
            WHERE window_end = (
                SELECT MAX(window_end) FROM trend_metrics WHERE asset = t.asset
            )
            ORDER BY asset
            """
        ).fetchall()
        dq_rows = conn.execute(
            "SELECT check_name, status, details, run_at FROM dq_check_results "
            "WHERE run_at = (SELECT MAX(run_at) FROM dq_check_results)"
        ).fetchall()

    trend_table = _rows_to_html_table(
        ["Asset", "Moving Avg (USD)", "Volatility", "Momentum (%)", "Trend", "As of"], trend_rows
    )
    dq_table = _rows_to_html_table(
        ["Check", "Status", "Details", "Run at"], dq_rows, status_col=1
    )

    return REPORT_TEMPLATE.substitute(
        report_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        trend_table=trend_table,
        dq_table=dq_table,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="data/market_data.db")
    parser.add_argument("--out", default="reports/output/daily_report.html")
    args = parser.parse_args()

    html = generate_report(Path(args.db_path))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    print(f"wrote report to {out_path}")


if __name__ == "__main__":
    main()
