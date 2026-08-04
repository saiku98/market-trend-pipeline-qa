"""Real-time market data ingestor.

Polls the public CoinGecko API on a fixed interval for a configurable list
of assets and persists each observation into a local SQLite store. Designed
to run as a long-lived process (e.g. `python -m ingestion.market_data_ingestor`)
or to be imported and driven from tests / a scheduler.

No API key is required: CoinGecko's `/simple/price` endpoint is public and
rate-limited generously enough for polling every 30-60 seconds.
"""
from __future__ import annotations

import argparse
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
DEFAULT_ASSETS = ("bitcoin", "ethereum", "solana")
DEFAULT_VS_CURRENCY = "usd"
DEFAULT_DB_PATH = Path("data/market_data.db")
DEFAULT_POLL_SECONDS = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


@dataclass(frozen=True)
class PricePoint:
    asset: str
    price_usd: float
    observed_at: str  # ISO-8601 UTC


class MarketDataIngestor:
    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        assets: Iterable[str] = DEFAULT_ASSETS,
        vs_currency: str = DEFAULT_VS_CURRENCY,
        session: requests.Session | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.assets = tuple(assets)
        self.vs_currency = vs_currency
        self.session = session or requests.Session()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS raw_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset TEXT NOT NULL,
                    price_usd REAL NOT NULL,
                    observed_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_raw_prices_asset_time "
                "ON raw_prices (asset, observed_at)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def fetch_once(self) -> list[PricePoint]:
        """Fetch current prices for all configured assets. Retries on failure."""
        params = {
            "ids": ",".join(self.assets),
            "vs_currencies": self.vs_currency,
        }
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.session.get(COINGECKO_URL, params=params, timeout=10)
                resp.raise_for_status()
                payload = resp.json()
                return self._parse(payload)
            except (requests.RequestException, ValueError) as exc:
                last_exc = exc
                logger.warning(
                    "fetch attempt %s/%s failed: %s", attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        assert last_exc is not None
        raise last_exc

    def _parse(self, payload: dict) -> list[PricePoint]:
        now = datetime.now(timezone.utc).isoformat()
        points: list[PricePoint] = []
        for asset in self.assets:
            entry = payload.get(asset)
            if not entry or self.vs_currency not in entry:
                logger.warning("no price returned for asset=%s", asset)
                continue
            points.append(
                PricePoint(asset=asset, price_usd=float(entry[self.vs_currency]), observed_at=now)
            )
        return points

    def persist(self, points: Iterable[PricePoint]) -> int:
        points = list(points)
        if not points:
            return 0
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO raw_prices (asset, price_usd, observed_at) VALUES (?, ?, ?)",
                [(p.asset, p.price_usd, p.observed_at) for p in points],
            )
        return len(points)

    def run_forever(self, poll_seconds: int = DEFAULT_POLL_SECONDS) -> None:
        logger.info(
            "starting ingestion loop assets=%s interval=%ss db=%s",
            self.assets, poll_seconds, self.db_path,
        )
        while True:
            try:
                points = self.fetch_once()
                n = self.persist(points)
                logger.info("persisted %s price points", n)
            except Exception:  # noqa: BLE001 - keep the loop alive
                logger.exception("ingestion cycle failed, will retry next interval")
            time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--assets", nargs="+", default=list(DEFAULT_ASSETS))
    parser.add_argument("--vs-currency", default=DEFAULT_VS_CURRENCY)
    parser.add_argument("--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--once", action="store_true", help="fetch a single snapshot and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    ingestor = MarketDataIngestor(
        db_path=Path(args.db_path), assets=args.assets, vs_currency=args.vs_currency
    )
    if args.once:
        points = ingestor.fetch_once()
        n = ingestor.persist(points)
        print(f"persisted {n} price points to {args.db_path}")
    else:
        ingestor.run_forever(poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    main()
