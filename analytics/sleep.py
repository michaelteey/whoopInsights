"""Deep sleep analytics — the things Whoop has the data for but doesn't surface.

Pulls from the `sleeps` table (excluding naps unless explicitly asked) and
derives:
  - rolling 14d sleep debt (need vs actual)
  - stage breakdown over time (deep / REM / light / awake)
  - disturbances per hour trend
  - weekday vs weekend split (social jet lag)
  - bedtime / wake-time consistency (chronotype drift)
"""
from __future__ import annotations

import sqlite3
import statistics
from datetime import datetime


# Whoop's sleep_needed.baseline isn't currently stored; treat 8h as the
# personal baseline until we wire that field through.
DEFAULT_BASELINE_HOURS = 8.0


def overview(conn: sqlite3.Connection, user_id: int) -> dict:
    """Top-line summary stats for the /sleep page."""
    last_night = conn.execute(
        """SELECT * FROM sleeps WHERE user_id = ? AND nap = 0
           ORDER BY end_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()

    avg_7d = _avg_asleep_hours(conn, user_id, days=7)
    avg_30d = _avg_asleep_hours(conn, user_id, days=30)
    avg_90d = _avg_asleep_hours(conn, user_id, days=90)
    debt_14d = _sleep_debt_hours(conn, user_id, days=14)
    efficiency_30d = _avg_metric(conn, user_id, "sleep_efficiency_pct", days=30)

    consistency = _bedtime_consistency(conn, user_id, days=14)

    return {
        "last_night": dict(last_night) if last_night else None,
        "asleep_avg_7d": round(avg_7d, 2) if avg_7d else None,
        "asleep_avg_30d": round(avg_30d, 2) if avg_30d else None,
        "asleep_avg_90d": round(avg_90d, 2) if avg_90d else None,
        "sleep_debt_14d_hours": round(debt_14d, 1) if debt_14d is not None else None,
        "efficiency_30d": round(efficiency_30d, 1) if efficiency_30d else None,
        "bedtime_stddev_min": consistency["bedtime_stddev_min"],
        "wake_stddev_min": consistency["wake_stddev_min"],
        "midpoint_stddev_min": consistency["midpoint_stddev_min"],
    }


def debt_curve(conn: sqlite3.Connection, user_id: int, days: int = 14) -> list[dict]:
    """Per-night need vs actual + running cumulative debt over the LAST N days.

    Cumulative resets at the start of the window — lifetime sleep debt is
    meaningless because it grows monotonically. 14 days is the default;
    30 is the longest sensible window.
    """
    rows = _nightly_asleep_rows(conn, user_id, days)
    cumulative = 0.0
    out = []
    for r in rows:
        actual = r["asleep_hours"]
        need = DEFAULT_BASELINE_HOURS
        debt = need - actual
        cumulative += debt
        out.append({
            "night": r["night"],
            "actual": round(actual, 2),
            "need": need,
            "debt": round(debt, 2),
            "cumulative": round(cumulative, 2),
        })
    return out


def stage_stacked(conn: sqlite3.Connection, user_id: int,
                  bucket: str = "week", days: int = 365) -> dict:
    """Stacked stage durations (in hours) by bucket. ApexCharts-ready."""
    fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}.get(bucket, "%Y-%W")
    rows = conn.execute(
        f"""
        SELECT strftime('{fmt}', start_at) AS bucket,
               SUM(total_slow_wave_sleep_milli) / 3600000.0 AS deep,
               SUM(total_rem_sleep_milli)       / 3600000.0 AS rem,
               SUM(total_light_sleep_milli)     / 3600000.0 AS light,
               SUM(total_awake_milli)           / 3600000.0 AS awake,
               COUNT(*) AS nights
        FROM sleeps
        WHERE user_id = ? AND nap = 0 AND start_at >= date('now', ?)
        GROUP BY bucket
        ORDER BY bucket ASC
        """,
        (user_id, f"-{days} days"),
    ).fetchall()
    if not rows:
        return {"labels": [], "datasets": []}
    labels = [r["bucket"] for r in rows]
    avg_per_night = lambda key: [
        round((r[key] or 0) / max(r["nights"], 1), 2) for r in rows
    ]
    return {
        "labels": labels,
        "datasets": [
            {"label": "deep",  "data": avg_per_night("deep")},
            {"label": "rem",   "data": avg_per_night("rem")},
            {"label": "light", "data": avg_per_night("light")},
            {"label": "awake", "data": avg_per_night("awake")},
        ],
    }


def disturbances_trend(conn: sqlite3.Connection, user_id: int,
                       bucket: str = "week",
                       days: int = 365) -> list[dict]:
    """Disturbance density over time — awake-minutes per asleep-hour, averaged
    over the selected bucket (day/week/month).

    We don't yet have raw disturbance counts; awake-time / asleep-time is a
    decent proxy and uses fields we already have.
    """
    fmt = {"day": "%Y-%m-%d", "week": "%Y-%W", "month": "%Y-%m"}.get(bucket, "%Y-%W")
    rows = conn.execute(
        f"""
        SELECT strftime('{fmt}', start_at) AS bucket,
               SUM(total_awake_milli) / 60000.0 AS awake_min,
               SUM(total_in_bed_milli - total_awake_milli) / 3600000.0 AS asleep_hours
        FROM sleeps
        WHERE user_id = ? AND nap = 0 AND start_at >= date('now', ?)
        GROUP BY bucket
        ORDER BY bucket ASC
        """,
        (user_id, f"-{days} days"),
    ).fetchall()
    out = []
    for r in rows:
        if not r["asleep_hours"] or r["asleep_hours"] <= 0:
            continue
        out.append({
            "day": r["bucket"],
            "value": round(r["awake_min"] / r["asleep_hours"], 2),
        })
    return out


def weekday_vs_weekend(conn: sqlite3.Connection, user_id: int,
                       days: int = 90) -> dict:
    """Compares weekday (Mon-Thu) vs weekend (Fri-Sun) sleep."""
    rows = conn.execute(
        """
        SELECT start_at, end_at,
               (total_in_bed_milli - total_awake_milli) / 3600000.0 AS asleep_hours
        FROM sleeps
        WHERE user_id = ? AND nap = 0 AND start_at >= date('now', ?)
        """,
        (user_id, f"-{days} days"),
    ).fetchall()

    weekday = {"asleep_hours": [], "bedtime_min": [], "wake_min": []}
    weekend = {"asleep_hours": [], "bedtime_min": [], "wake_min": []}

    for r in rows:
        try:
            dt_start = datetime.fromisoformat(r["start_at"].replace("Z", "+00:00"))
            dt_end = datetime.fromisoformat(r["end_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        # Friday/Saturday/Sunday nights as "weekend" — i.e. nights leading
        # into the next morning being a non-school/work day.
        bucket = weekend if dt_start.weekday() >= 4 else weekday
        bucket["asleep_hours"].append(r["asleep_hours"])
        bucket["bedtime_min"].append(_clock_minutes(dt_start))
        bucket["wake_min"].append(_clock_minutes(dt_end))

    def _mean(xs):
        return round(statistics.mean(xs), 2) if xs else None

    return {
        "weekday": {
            "n": len(weekday["asleep_hours"]),
            "asleep_hours_mean": _mean(weekday["asleep_hours"]),
            "bedtime_mean": _format_clock(_mean_clock(weekday["bedtime_min"])),
            "wake_mean":    _format_clock(_mean_clock(weekday["wake_min"])),
        },
        "weekend": {
            "n": len(weekend["asleep_hours"]),
            "asleep_hours_mean": _mean(weekend["asleep_hours"]),
            "bedtime_mean": _format_clock(_mean_clock(weekend["bedtime_min"])),
            "wake_mean":    _format_clock(_mean_clock(weekend["wake_min"])),
        },
    }


# ---- helpers ------------------------------------------------------------

def _avg_asleep_hours(conn, user_id, days):
    row = conn.execute(
        """
        SELECT AVG((total_in_bed_milli - total_awake_milli) / 3600000.0) AS v
        FROM sleeps
        WHERE user_id = ? AND nap = 0 AND start_at >= date('now', ?)
        """,
        (user_id, f"-{days} days"),
    ).fetchone()
    return float(row["v"]) if row and row["v"] is not None else None


def _avg_metric(conn, user_id, col, days):
    row = conn.execute(
        f"SELECT AVG({col}) AS v FROM sleeps WHERE user_id = ? AND nap = 0 AND start_at >= date('now', ?)",
        (user_id, f"-{days} days"),
    ).fetchone()
    return float(row["v"]) if row and row["v"] is not None else None


def _sleep_debt_hours(conn, user_id, days):
    row = conn.execute(
        f"""
        SELECT SUM(? - (total_in_bed_milli - total_awake_milli) / 3600000.0) AS debt
        FROM sleeps
        WHERE user_id = ? AND nap = 0 AND start_at >= date('now', ?)
        """,
        (DEFAULT_BASELINE_HOURS, user_id, f"-{days} days"),
    ).fetchone()
    return float(row["debt"]) if row and row["debt"] is not None else None


def _nightly_asleep_rows(conn, user_id, days):
    rows = conn.execute(
        """
        SELECT substr(start_at, 1, 10) AS night,
               (total_in_bed_milli - total_awake_milli) / 3600000.0 AS asleep_hours,
               total_awake_milli / 60000.0 AS awake_min
        FROM sleeps
        WHERE user_id = ? AND nap = 0 AND start_at >= date('now', ?)
        ORDER BY start_at ASC
        """,
        (user_id, f"-{days} days"),
    ).fetchall()
    return [dict(r) for r in rows]


def _bedtime_consistency(conn, user_id, days):
    rows = conn.execute(
        """SELECT start_at, end_at FROM sleeps
           WHERE user_id = ? AND nap = 0 AND start_at >= date('now', ?)""",
        (user_id, f"-{days} days"),
    ).fetchall()
    bedtimes, wakes, midpoints = [], [], []
    for r in rows:
        try:
            s = datetime.fromisoformat(r["start_at"].replace("Z", "+00:00"))
            e = datetime.fromisoformat(r["end_at"].replace("Z", "+00:00"))
        except Exception:
            continue
        bedtimes.append(_clock_minutes(s))
        wakes.append(_clock_minutes(e))
        midpoints.append((_clock_minutes(s) + _clock_minutes(e) + 720) / 2 % 1440)
    def _stdev(xs):
        return round(statistics.pstdev(xs), 1) if len(xs) > 1 else None
    return {
        "bedtime_stddev_min": _stdev(bedtimes),
        "wake_stddev_min": _stdev(wakes),
        "midpoint_stddev_min": _stdev(midpoints),
    }


def _clock_minutes(dt: datetime) -> int:
    """Minutes from midnight, wrapping so e.g. 23:30 stays 1410 not -30."""
    return dt.hour * 60 + dt.minute


def _mean_clock(minutes_list):
    return statistics.mean(minutes_list) if minutes_list else None


def _format_clock(m):
    if m is None:
        return None
    m = int(round(m)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"
