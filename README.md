# Market Trend Pipeline QA

A small real-time market data pipeline paired with an independent,
two-language (Python + Java) data-quality validation layer — built as a
portfolio project focused on pipeline/report/dashboard testing rather than
just the pipeline itself.

**What it does:** polls live crypto prices, computes rolling trend
indicators (moving average, volatility, momentum), validates the output
against a battery of data-quality checks in both Python and Java, and
surfaces the result in a live dashboard and a daily HTML report.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full diagram and
design notes.

| Stage | Component | Tech |
|---|---|---|
| Ingest | `ingestion/market_data_ingestor.py` | Python, CoinGecko public API, SQLite |
| Store | `warehouse/schema.sql`, `warehouse/loader.py` | SQL (SQLite locally / Postgres-portable) |
| Transform | `spark_jobs/trend_forecast.py` | PySpark (prod) / Pandas (local & CI) |
| Validate | `validation/python/checks.py` | Python, pytest |
| Validate (independent re-check) | `validation/java/` | Java, JDBC, JUnit 5, Maven |
| Serve | `dashboard/app.py`, `reports/daily_report_generator.py` | Streamlit, HTML |
| CI | `.github/workflows/ci.yml` | GitHub Actions |

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 1. set up the warehouse
python -m warehouse.loader --db-path data/market_data.db

# 2. grab a snapshot of live prices (no API key needed)
python -m ingestion.market_data_ingestor --once --db-path data/market_data.db
# ...or run continuously:
python -m ingestion.market_data_ingestor --db-path data/market_data.db --poll-seconds 30 -v

# 3. compute trend indicators (run this periodically as new ticks land)
python spark_jobs/trend_forecast.py --db-path data/market_data.db

# 4. validate
python -m validation.python.checks --db-path data/market_data.db
mvn -f validation/java/pom.xml test

# 5. look at it
streamlit run dashboard/app.py -- --db-path data/market_data.db
python reports/daily_report_generator.py --db-path data/market_data.db
```

## Testing

```bash
pytest                              # Python unit tests
mvn -f validation/java/pom.xml test # Java validation unit tests
ruff check .                        # lint
```

All of the above run in CI on every pull request — see
[.github/workflows/ci.yml](.github/workflows/ci.yml).

## Project layout

```
ingestion/        real-time price polling -> SQLite
warehouse/         schema, loader, and the SQL used by both validation layers
spark_jobs/        trend/momentum computation (pandas locally, Spark in prod)
validation/python/ data-quality checks (pytest)
validation/java/   independent JDBC-based data-quality checks (JUnit, Maven)
dashboard/         Streamlit live view
reports/           daily HTML summary report generator
tests/             pytest suite covering ingestion, transform, validation, reports
docs/              architecture notes
```

## License

MIT — see [LICENSE](LICENSE).
