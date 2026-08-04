"""Streamlit dashboard for the market trend pipeline.

Shows live price ticks and rolling trend indicators straight from the
warehouse. Run with:

    streamlit run dashboard/app.py -- --db-path data/market_data.db
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

DEFAULT_DB_PATH = "data/market_data.db"


def _db_path() -> str:
    # Streamlit swallows argv, so accept --db-path after `--` or fall back.
    if "--db-path" in sys.argv:
        idx = sys.argv.index("--db-path")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return DEFAULT_DB_PATH


@st.cache_data(ttl=15)
def load_prices(db_path: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT asset, price_usd, observed_at FROM raw_prices ORDER BY observed_at", conn
        )


@st.cache_data(ttl=15)
def load_trends(db_path: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT asset, window_end, moving_avg_usd, volatility, momentum, trend_label "
            "FROM trend_metrics ORDER BY window_end",
            conn,
        )


@st.cache_data(ttl=15)
def load_latest_dq_status(db_path: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            "SELECT check_name, status, details, run_at FROM dq_check_results "
            "ORDER BY run_at DESC LIMIT 20",
            conn,
        )


def main() -> None:
    st.set_page_config(page_title="Market Trend Pipeline", layout="wide")
    st.title("Real-Time Market Trend Dashboard")

    db_path = _db_path()
    if not Path(db_path).exists():
        st.warning(
            f"No warehouse database found at `{db_path}`. Run the ingestor and "
            "trend job first (see README)."
        )
        return

    prices = load_prices(db_path)
    trends = load_trends(db_path)
    dq_status = load_latest_dq_status(db_path)

    assets = sorted(prices["asset"].unique()) if not prices.empty else []
    selected = st.multiselect("Assets", assets, default=assets)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Live price")
        if not prices.empty and selected:
            chart_df = prices[prices["asset"].isin(selected)].pivot(
                index="observed_at", columns="asset", values="price_usd"
            )
            st.line_chart(chart_df)
        else:
            st.info("No price data yet.")

    with col2:
        st.subheader("Moving average & volatility")
        if not trends.empty and selected:
            chart_df = trends[trends["asset"].isin(selected)].pivot(
                index="window_end", columns="asset", values="moving_avg_usd"
            )
            st.line_chart(chart_df)
        else:
            st.info("No trend data yet.")

    st.subheader("Latest trend labels")
    if not trends.empty:
        latest = trends.sort_values("window_end").groupby("asset").tail(1)
        st.dataframe(latest, use_container_width=True)
    else:
        st.info("No trend data yet.")

    st.subheader("Data-quality check history")
    if not dq_status.empty:
        st.dataframe(dq_status, use_container_width=True)
    else:
        st.info("No data-quality checks have run yet.")


if __name__ == "__main__":
    main()
