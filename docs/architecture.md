# Architecture

```
                 +--------------------+
 CoinGecko API   |  ingestion/        |
 (public, no key)| market_data_       |   polls every 30s, writes ticks
  ─────────────► |  ingestor.py       │─────────────┐
                 +--------------------+              │
                                                       ▼
                                            +---------------------+
                                            |  warehouse (SQLite   |
                                            |  locally / Postgres  |
                                            |  in prod)            |
                                            |  raw_prices          |
                                            +----------+-----------+
                                                       │
                        ┌──────────────────────────────┼──────────────────────────┐
                        ▼                              ▼                          ▼
             +-------------------+          +---------------------+   +----------------------+
             | spark_jobs/       |          | validation/python/   |   | validation/java/      |
             | trend_forecast.py |─────────►| checks.py            |   | (independent JDBC     |
             | (pandas engine    |  writes  | freshness, null,     |   |  re-check, JUnit)      |
             |  locally, Spark   |  trend_  | duplicate, range,    |   +----------------------+
             |  in prod)         |  metrics | label validity       |
             +-------------------+          +----------+-----------+
                                                        │ logs to dq_check_results
                                                        ▼
                                  +----------------------------------------+
                                  | dashboard/app.py (Streamlit, live)     |
                                  | reports/daily_report_generator.py      |
                                  | (static HTML summary)                  |
                                  +----------------------------------------+
```

## Why two validation layers (Python and Java)

`validation/python/checks.py` and `validation/java/` check overlapping
invariants (freshness, nulls/ranges, duplicates, valid trend labels) but are
implemented independently, in different languages, against the same SQL
warehouse. The idea, borrowed from how QA teams validate ETL pipelines in
practice: a bug in one implementation (an off-by-one in a SQL query, a wrong
comparison operator) is unlikely to be reproduced identically in the other,
so running both in CI catches more classes of regression than either alone.

## Local vs. production

Everything in this repo runs locally against SQLite with no external
services, so the whole pipeline (ingest → transform → validate → report) is
runnable end-to-end from a laptop. The pieces that would change in a
production deployment are called out in code comments:

- `warehouse/schema.sql` — same DDL, swap SQLite-specific `AUTOINCREMENT` for
  Postgres `SERIAL`/`IDENTITY`.
- `spark_jobs/trend_forecast.py` — `--engine spark` runs the real PySpark
  Structured API path against a cluster; `--engine pandas` (default) is used
  for local dev and CI.
- `ingestion/market_data_ingestor.py` — `run_forever()` is meant to run as a
  long-lived worker process, not as a scheduled job.
