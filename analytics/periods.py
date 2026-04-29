"""Period-comparison summaries for the dashboard stat cards.

For each metric (recovery, HRV, RHR, strain, sleep performance) we compute
the average over each lookback window (1d/7d/30d/90d/6m) and the delta vs
the immediately preceding window of the same length — so the user can see
both 'how am I right now' and 'is the trend going the right way'.
"""
from __future__ import annotations

import sqlite3


PERIODS = [
    (1,   "1d"),
    (7,   "7d"),
    (30,  "30d"),
    (90,  "90d"),
    (180, "6m"),
]


METRICS = {
    # key: (table, column, time-column, formatter)
    "recovery":          ("recoveries", "recovery_score",        "recorded_at", "pct"),
    "hrv":               ("recoveries", "hrv_rmssd_milli",       "recorded_at", "ms"),
    "rhr":               ("recoveries", "resting_heart_rate",    "recorded_at", "bpm"),
    "strain":            ("cycles",     "strain",                "start_at",    "decimal"),
    "sleep_performance": ("sleeps",     "sleep_performance_pct", "start_at",    "pct"),
}


def period_summary(conn: sqlite3.Connection, user_id: int) -> dict:
    """Returns:
        {
            "recovery": {
                "1d":  {"value": 65.0, "prev": 70.5, "delta": -5.5,
                         "delta_pct": -7.8},
                "7d":  {...},
                ...
            },
            "hrv":  {...},
            ...
        }
    'value' is the average over the last N days. 'prev' is the average over
    the N days before that window. 'delta' is value - prev. 'delta_pct' is
    delta as a percentage of prev (or None if prev was zero/null).
    Missing data is returned as None so the template can show '—'.
    """
    out: dict = {}
    for metric, (table, col, time_col, _fmt) in METRICS.items():
        out[metric] = {}
        for days, label in PERIODS:
            cur = _avg(conn, user_id, table, col, time_col, days, 0)
            prev = _avg(conn, user_id, table, col, time_col, days * 2, days)
            delta = (cur - prev) if (cur is not None and prev is not None) else None
            delta_pct = None
            if delta is not None and prev:
                delta_pct = (delta / prev) * 100
            out[metric][label] = {
                "value": cur,
                "prev": prev,
                "delta": delta,
                "delta_pct": delta_pct,
            }
    return out


def _avg(conn, user_id, table, col, time_col, lookback_days, offset_days) -> float | None:
    """Average of `col` over [now - lookback_days, now - offset_days]."""
    sql = f"""
        SELECT AVG({col}) AS v
        FROM {table}
        WHERE user_id = ?
          AND {time_col} >= datetime('now', ?)
          AND {time_col} <  datetime('now', ?)
    """
    row = conn.execute(
        sql, (user_id, f"-{lookback_days} days", f"-{offset_days} days")
    ).fetchone()
    v = row["v"] if row else None
    return float(v) if v is not None else None
