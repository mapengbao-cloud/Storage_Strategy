"""Database access layer — connection pool, query helpers, preset queries.

Extracts and unifies the pymysql connection code duplicated across:
- 06 DataMining/db_viewer.py
- 06 DataMining/extract_reserve_data.py
- 06 DataMining/prescheduling_server.py
- 06 DataMining/intraday_viz.py

Usage:
    from src.data.db import query, query_to_dataframe
    rows = query("SELECT * FROM some_table WHERE date = %s", (date_str,))
"""

import os
import pymysql
import pymysql.cursors
import pandas as pd
from contextlib import contextmanager
from typing import Any
from src.config import get_settings


def _get_db_config() -> dict:
    """Build pymysql connection kwargs from settings (with env var fallback).

    Settings values may contain un-expanded ${ENV_VAR} if config.py
    didn't process them. This provides a fallback using os.getenv.
    """
    settings = get_settings()
    db = settings.get("database", {}).get("tianrun", {})

    def _resolve(key: str, default: str) -> str:
        val = db.get(key, default)
        if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
            env_key = val[2:-1]
            return os.getenv(env_key, default)
        return val

    return {
        "host": _resolve("host", "rm-2zej7q7186wi4eds5no.mysql.rds.aliyuncs.com"),
        "port": int(_resolve("port", "3306")),
        "user": _resolve("user", "pengyiqiang"),
        "password": _resolve("password", ""),
        "database": _resolve("database", "tianrun_new"),
        "charset": _resolve("charset", "utf8mb4"),
        "cursorclass": pymysql.cursors.DictCursor,
        "connect_timeout": 30,
    }


@contextmanager
def get_connection():
    """Yield a pymysql connection from settings config.

    Usage:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ...")
                rows = cur.fetchall()
    """
    cfg = _get_db_config()
    conn = pymysql.connect(**cfg)
    try:
        yield conn
    finally:
        conn.close()


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a SELECT query and return results as list of dicts.

    Args:
        sql: SQL query string with %s placeholders.
        params: Tuple of query parameters.

    Returns:
        List of dicts keyed by column name.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def query_to_dataframe(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Execute a SELECT query and return results as a pandas DataFrame.

    Args:
        sql: SQL query string.
        params: Query parameters.

    Returns:
        DataFrame with column names from the query.
    """
    with get_connection() as conn:
        return pd.read_sql(sql, conn, params=params)


# ── Preset Queries ──────────────────────────────────────────────

# 润津储能 member_id (also configurable via settings)
MEMBER_ID = "b9e64e64a713458eba94c9af05c0a757"


def query_clearing_prices(
    date_str: str, market: str = "dayahead"
) -> list[dict]:
    """Query 96-point clearing prices for Runjin station.

    Args:
        date_str: ISO date (e.g. '2026-05-22').
        market: 'dayahead' or 'realtime'.

    Returns:
        List of 96 dicts with time_point and price fields.
    """
    table = (
        "shandong_px_spot_dayahead_clearing_price"
        if market == "dayahead"
        else "shandong_px_spot_realtime_clearing_price"
    )
    sql = f"""
        SELECT time_point, clearing_price as price
        FROM {table}
        WHERE member_id = %s AND date = %s
        ORDER BY time_point
    """
    return query(sql, (MEMBER_ID, date_str))


def query_settlement_v3(date_str: str) -> dict:
    """Query v3 settlement data for one date, split by 发电/用电.

    Returns:
        {'generate': [96 dicts], 'load': [24 dicts]}
    """
    sql = """
        SELECT current_unit, analysis_field, time_point, value
        FROM shandong_px_statement_spot_daily_v3
        WHERE member_id = %s AND date = %s
        ORDER BY current_unit, time_point, analysis_field
    """
    rows = query(sql, (MEMBER_ID, date_str))
    result = {"generate": [], "load": []}
    for row in rows:
        unit = "generate" if row["current_unit"] == "发电" else "load"
        result[unit].append(row)
    return result


def query_prescheduling(date_str: str) -> list[dict]:
    """Query provincial prescheduling results for one date."""
    sql = """
        SELECT generator_name, time_point, power_output, price
        FROM shandong_px_provincial_prescheduling_results
        WHERE date = %s
        ORDER BY generator_name, time_point
    """
    return query(sql, (date_str,))


def query_reserve_capacity(start: str, end: str) -> list[dict]:
    """Query day-ahead and actual reserve capacity for a date range."""
    results = []
    for table_type, label in [
        ("dayahead", "日前"),
        ("actual", "实际"),
    ]:
        table = f"shandong_px_spot_{table_type}_reserve_capacity_info"
        sql = f"""
            SELECT date, time_point, positive_reserve, negative_reserve
            FROM {table}
            WHERE date BETWEEN %s AND %s
            ORDER BY date, time_point
        """
        rows = query(sql, (start, end))
        for r in rows:
            r["type"] = label
        results.extend(rows)
    return results


def query_supply_demand(start: str, end: str,
                        fore_type: str = "日前预测") -> list[dict]:
    """Query supply & demand forecast data.

    Args:
        start, end: ISO date range.
        fore_type: '日前预测' or '实时预测'.

    Returns:
        List of dicts with date, time_point, supply, demand, etc.
    """
    sql = """
        SELECT date, time_point, system_load_forecast as demand,
               tie_line_forecast, wind_forecast, solar_forecast
        FROM all_province_supply_and_demand_forecast
        WHERE date BETWEEN %s AND %s AND fore_type = %s
        ORDER BY date, time_point
    """
    return query(sql, (start, end, fore_type))


def query_price_forecast(
    date_str: str, price_type: int = 1
) -> list[dict]:
    """Query price forecast from algorithm_clearing_price_forecast table.

    Args:
        date_str: ISO date string.
        price_type: 1=日前, 2=实时.

    Returns:
        List of 96 dicts with time_point and price fields.
    """
    sql = """
        SELECT time_point, clearing_price as price
        FROM algorithm_clearing_price_forecast
        WHERE date = %s AND price_type = %s
        ORDER BY time_point
    """
    return query(sql, (date_str, price_type))


def query_load_info(
    date_str: str, data_type: str = "actual"
) -> dict[str, list[float]]:
    """Query 96-point load info (dispatched, tie-line, wind, solar).

    Args:
        date_str: ISO date string.
        data_type: 'actual' or 'dayahead'.

    Returns:
        {'dispatched': [96], 'tie_line': [96], 'wind': [96], 'solar': [96]}
    """
    table = (
        "shandong_px_spot_actual_load_info"
        if data_type == "actual"
        else "shandong_px_spot_dayahead_load_info"
    )
    sql = f"""
        SELECT time_point, dispatched_load, tie_line_load,
               wind_power, solar_power
        FROM {table}
        WHERE date = %s
        ORDER BY time_point
    """
    rows = query(sql, (date_str,))
    return {
        "dispatched": [float(r.get("dispatched_load") or 0) for r in rows],
        "tie_line": [float(r.get("tie_line_load") or 0) for r in rows],
        "wind": [float(r.get("wind_power") or 0) for r in rows],
        "solar": [float(r.get("solar_power") or 0) for r in rows],
    }


# ── DA-RT Deviation & Weather Queries ───────────────────────────

def query_da_rt_price_pairs(
    start: str, end: str
) -> list[dict]:
    """Fetch paired day-ahead and real-time clearing prices.

    Joins the day-ahead and real-time clearing price tables on
    (date, time_point) for Runjin station.

    Args:
        start, end: ISO date range strings.

    Returns:
        List of dicts with keys: date, time_point, da_price, rt_price.
    """
    sql = """
        SELECT
            da.date,
            da.time_point,
            da.clearing_price AS da_price,
            rt.clearing_price AS rt_price
        FROM shandong_px_spot_dayahead_clearing_price da
        LEFT JOIN shandong_px_spot_realtime_clearing_price rt
            ON da.date = rt.date
            AND da.time_point = rt.time_point
            AND rt.member_id = %s
        WHERE da.member_id = %s
            AND da.date BETWEEN %s AND %s
        ORDER BY da.date, da.time_point
    """
    return query(sql, (MEMBER_ID, MEMBER_ID, start, end))


def query_da_rt_price_pairs_96point(
    date_str: str
) -> dict[str, list[float]] | None:
    """Fetch paired DA/RT prices at 96-point resolution for one date.

    Uses algorithm_clearing_price_forecast table which has both
    price_type=1 (日前) and price_type=2 (实时) at 96-point resolution.

    Args:
        date_str: ISO date string.

    Returns:
        {'da': [96], 'rt': [96]} or None if data missing.
    """
    sql = """
        SELECT time_point, price_type, clearing_price as price
        FROM algorithm_clearing_price_forecast
        WHERE date = %s AND price_type IN (1, 2)
        ORDER BY price_type, time_point
    """
    rows = query(sql, (date_str,))

    if not rows:
        return None

    da_prices = [0.0] * 96
    rt_prices = [0.0] * 96

    for r in rows:
        tp = r["time_point"] - 1  # 1-based to 0-based
        if tp < 0 or tp >= 96:
            continue
        price = float(r["price"]) if r["price"] else 0.0
        if r["price_type"] == 1:
            da_prices[tp] = price
        elif r["price_type"] == 2:
            rt_prices[tp] = price

    return {"da": da_prices, "rt": rt_prices}


def query_historical_weather(
    start: str, end: str
) -> list[dict]:
    """Query historical weather data from database.

    Table: all_province_weather_data_mtl_forecast.
    Falls back gracefully if table is empty or absent.

    Args:
        start, end: ISO date range.

    Returns:
        List of dicts with weather fields.
    """
    sql = """
        SELECT date, province, temperature, humidity,
               wind_speed, cloud_cover, radiation
        FROM all_province_weather_data_mtl_forecast
        WHERE date BETWEEN %s AND %s
            AND province = '山东'
        ORDER BY date
    """
    try:
        return query(sql, (start, end))
    except Exception:
        return []  # Table may not exist or be empty