import sqlite3
from pathlib import Path

import pytest

from ingestion.market_data_ingestor import MarketDataIngestor, PricePoint


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return FakeResponse(self._payload)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test_market_data.db"


def test_ensure_schema_creates_table(db_path):
    session = FakeSession({"bitcoin": {"usd": 50000.0}})
    MarketDataIngestor(db_path=db_path, assets=["bitcoin"], session=session)

    conn = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "raw_prices" in tables


def test_fetch_once_parses_known_assets(db_path):
    session = FakeSession({"bitcoin": {"usd": 50000.0}, "ethereum": {"usd": 3000.0}})
    ingestor = MarketDataIngestor(
        db_path=db_path, assets=["bitcoin", "ethereum"], session=session
    )

    points = ingestor.fetch_once()

    assert len(points) == 2
    assert {p.asset for p in points} == {"bitcoin", "ethereum"}
    assert all(isinstance(p.price_usd, float) for p in points)


def test_fetch_once_skips_missing_asset(db_path):
    session = FakeSession({"bitcoin": {"usd": 50000.0}})
    ingestor = MarketDataIngestor(
        db_path=db_path, assets=["bitcoin", "made-up-coin"], session=session
    )

    points = ingestor.fetch_once()

    assert len(points) == 1
    assert points[0].asset == "bitcoin"


def test_persist_writes_rows(db_path):
    session = FakeSession({"bitcoin": {"usd": 50000.0}})
    ingestor = MarketDataIngestor(db_path=db_path, assets=["bitcoin"], session=session)
    points = [PricePoint(asset="bitcoin", price_usd=50000.0, observed_at="2026-08-04T00:00:00+00:00")]

    n = ingestor.persist(points)

    assert n == 1
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT asset, price_usd FROM raw_prices").fetchone()
    assert row == ("bitcoin", 50000.0)


def test_persist_empty_list_is_noop(db_path):
    session = FakeSession({"bitcoin": {"usd": 50000.0}})
    ingestor = MarketDataIngestor(db_path=db_path, assets=["bitcoin"], session=session)

    assert ingestor.persist([]) == 0
