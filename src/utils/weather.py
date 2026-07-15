"""Weather API client — Open-Meteo free weather forecast API.

Usage:
    from src.utils.weather import fetch_weather_forecast
    data = fetch_weather_forecast(days=7)
"""

import json
import urllib.request
import urllib.parse
from datetime import date, timedelta
from src.config import get_settings


def _get_weather_config() -> dict:
    """Get weather API configuration from settings."""
    return get_settings()["weather"]


def fetch_weather_forecast(days: int = 7) -> dict | None:
    """Fetch weather forecast from Open-Meteo API.

    Args:
        days: Forecast horizon in days (default 7, max 16).

    Returns:
        Parsed JSON response dict, or None on failure.
        Key fields: hourly.temperature_2m, hourly.relative_humidity_2m,
        hourly.wind_speed_10m, hourly.shortwave_radiation, hourly.cloud_cover.
    """
    cfg = _get_weather_config()
    params = {
        "latitude": cfg["latitude"],
        "longitude": cfg["longitude"],
        "hourly": (
            "temperature_2m,relative_humidity_2m,"
            "wind_speed_10m,wind_direction_10m,"
            "shortwave_radiation,direct_radiation,"
            "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high"
        ),
        "timezone": cfg["timezone"],
        "forecast_days": days,
        "wind_speed_unit": "ms",
    }
    url = f"{cfg['api']}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StorageStrategy/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"[WARN] Weather API fetch failed: {e}")
        return None


def extract_daily_weather(forecast: dict, target_date: str) -> dict | None:
    """Extract daily aggregated weather data for a specific date.

    Args:
        forecast: Full forecast dict from fetch_weather_forecast().
        target_date: ISO date string like '2026-06-15'.

    Returns:
        Dict with daily averages: temp_avg, humidity_avg, wind_avg,
        radiation_max, cloud_cover_avg, or None if date not found.
    """
    if not forecast or "hourly" not in forecast:
        return None

    hourly = forecast["hourly"]
    times = hourly.get("time", [])

    # Filter to target date
    indices = [i for i, t in enumerate(times) if t.startswith(target_date)]
    if not indices:
        return None

    def _avg(key):
        vals = [hourly[key][i] for i in indices if hourly[key][i] is not None]
        return sum(vals) / len(vals) if vals else None

    def _max(key):
        vals = [hourly[key][i] for i in indices if hourly[key][i] is not None]
        return max(vals) if vals else None

    return {
        "date": target_date,
        "temp_avg": _avg("temperature_2m"),
        "humidity_avg": _avg("relative_humidity_2m"),
        "wind_speed_avg": _avg("wind_speed_10m"),
        "radiation_max": _max("shortwave_radiation"),
        "cloud_cover_avg": _avg("cloud_cover"),
    }