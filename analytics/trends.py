"""Long-range trend queries that Whoop itself caps at 6 months."""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta


def daily_series(conn: sqlite3.Connection, user_id: int, days: int) -> dict:
    """Pull HRV / RHR / recovery / strain / sleep performance per day."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    cycles = conn.execute(
        """
        SELECT substr(start_at, 1, 10) AS day,
               AVG(strain) AS strain
        FROM cycles
        WHERE user_id = ? AND start_at >= ?
        GROUP BY day
        ORDER BY day ASC
        """,
        (user_id, since),
    ).fetchall()

    recoveries = conn.execute(
        """
        SELECT substr(recorded_at, 1, 10) AS day,
               AVG(recovery_score)     AS recovery,
               AVG(hrv_rmssd_milli)    AS hrv,
               AVG(resting_heart_rate) AS rhr
        FROM recoveries
        WHERE user_id = ? AND recorded_at >= ?
        GROUP BY day
        ORDER BY day ASC
        """,
        (user_id, since),
    ).fetchall()

    sleeps = conn.execute(
        """
        SELECT substr(start_at, 1, 10) AS day,
               AVG(sleep_performance_pct) AS sleep_perf,
               SUM(total_in_bed_milli - total_awake_milli) AS asleep_milli
        FROM sleeps
        WHERE user_id = ? AND start_at >= ? AND nap = 0
        GROUP BY day
        ORDER BY day ASC
        """,
        (user_id, since),
    ).fetchall()

    return {
        "strain": [{"day": r["day"], "value": r["strain"]} for r in cycles],
        "recovery": [{"day": r["day"], "value": r["recovery"]} for r in recoveries],
        "hrv": [{"day": r["day"], "value": r["hrv"]} for r in recoveries],
        "rhr": [{"day": r["day"], "value": r["rhr"]} for r in recoveries],
        "sleep_performance": [{"day": r["day"], "value": r["sleep_perf"]} for r in sleeps],
        "sleep_hours": [
            {"day": r["day"], "value": (r["asleep_milli"] or 0) / 3_600_000}
            for r in sleeps
        ],
    }
