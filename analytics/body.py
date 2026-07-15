"""Body composition (weight, body-fat) trends and correlation analysis.

Whoop's /v2/user/measurement/body only returns current values, so we build
the time series ourselves by snapshotting on every sync. Correlations use
week-over-week weight change against weekly-averaged behaviour metrics.

We keep the maths in pure Python — no numpy dependency — since the point
counts are small (weeks, not milliseconds).
"""
from __future__ import annotations

import math
import sqlite3


def weight_series(conn: sqlite3.Connection, user_id: int,
                  days: int = 365) -> list[dict]:
    """Every recorded weight point over the lookback window."""
    rows = conn.execute(
        """SELECT recorded_at, weight_kg, body_fat_pct
           FROM body_measurements
           WHERE user_id = ?
                 AND weight_kg IS NOT NULL
                 AND recorded_at >= date('now', ?)
           ORDER BY recorded_at ASC""",
        (user_id, f"-{days} days"),
    ).fetchall()
    return [
        {"date": r["recorded_at"][:10],
         "weight_kg": round(r["weight_kg"], 2),
         "body_fat_pct": r["body_fat_pct"]}
        for r in rows
    ]


def summary(conn: sqlite3.Connection, user_id: int) -> dict:
    """Top-line stats for the /body page."""
    rows = conn.execute(
        """SELECT recorded_at, weight_kg, body_fat_pct, height_m
           FROM body_measurements
           WHERE user_id = ? AND weight_kg IS NOT NULL
           ORDER BY recorded_at DESC""",
        (user_id,),
    ).fetchall()
    if not rows:
        return {"current": None, "earliest": None, "delta_kg": None,
                "bmi": None, "n_points": 0}

    current = dict(rows[0])
    earliest = dict(rows[-1])
    delta = round(current["weight_kg"] - earliest["weight_kg"], 2)
    bmi = None
    if current["weight_kg"] and current["height_m"]:
        bmi = round(current["weight_kg"] / (current["height_m"] ** 2), 1)
    return {
        "current": current,
        "earliest": earliest,
        "delta_kg": delta,
        "bmi": bmi,
        "n_points": len(rows),
    }


# --- Correlations --------------------------------------------------------

# Everything we can plausibly correlate with weight change.
# key -> (SQL to compute a per-week average / total)
_METRICS_SQL = {
    "strain":   ("cycles",     "AVG(strain)",          "start_at"),
    "kj_burnt": ("workouts",   "SUM(kilojoule)",       "start_at"),
    "workouts_n": ("workouts", "COUNT(*)",             "start_at"),
    "sleep_hours": ("sleeps",  "AVG((total_in_bed_milli - total_awake_milli) / 3600000.0)",
                               "start_at"),
    "hrv":      ("recoveries", "AVG(hrv_rmssd_milli)", "recorded_at"),
    "rhr":      ("recoveries", "AVG(resting_heart_rate)", "recorded_at"),
    "recovery": ("recoveries", "AVG(recovery_score)",  "recorded_at"),
}

_METRIC_LABELS = {
    "strain": "daily strain",
    "kj_burnt": "kJ burnt per week",
    "workouts_n": "workouts per week",
    "sleep_hours": "sleep duration",
    "hrv": "HRV (RMSSD)",
    "rhr": "resting HR",
    "recovery": "recovery score",
}


def correlations(conn: sqlite3.Connection, user_id: int,
                 lookback_days: int = 365,
                 min_pairs: int = 4) -> list[dict]:
    """Pearson r between weekly weight-change and each candidate driver.

    For each ISO-week bucket in the window:
      - weight for that week = mean of measurements landing in the week
        (or the most recent measurement if a measurement predates the week)
      - metric for that week = SUM/AVG of the metric over the week
      - delta_weight = weight[i] - weight[i-1]

    Then Pearson r on (metric[i], delta_weight[i]) pairs. Returns one row
    per metric sorted by |r| desc. Metrics with < min_pairs valid weeks
    are dropped."""
    weeks = _weekly_weight(conn, user_id, lookback_days)
    if len(weeks) < min_pairs + 1:
        return []

    out = []
    for key, (table, expr, time_col) in _METRICS_SQL.items():
        metric_by_week = _weekly_metric(conn, user_id, table, expr, time_col,
                                        lookback_days)
        xs, ys = [], []
        prev_w = None
        for week_key, weight in weeks:
            if prev_w is not None and week_key in metric_by_week:
                m_val = metric_by_week[week_key]
                if m_val is not None:
                    xs.append(m_val)
                    ys.append(weight - prev_w)
            prev_w = weight
        r = _pearson(xs, ys)
        if r is None:
            continue
        p = _p_value(r, len(xs))
        out.append({
            "metric": key,
            "label": _METRIC_LABELS[key],
            "r": round(r, 3),
            "p": round(p, 4) if p is not None else None,
            "n": len(xs),
            "direction": _direction(key, r),
        })

    out.sort(key=lambda d: -abs(d["r"]))
    return out


def _weekly_weight(conn, user_id, days) -> list[tuple[str, float]]:
    rows = conn.execute(
        """SELECT strftime('%Y-%W', recorded_at) AS wk,
                  AVG(weight_kg) AS w
           FROM body_measurements
           WHERE user_id = ? AND weight_kg IS NOT NULL
                 AND recorded_at >= date('now', ?)
           GROUP BY wk
           ORDER BY wk ASC""",
        (user_id, f"-{days} days"),
    ).fetchall()
    return [(r["wk"], float(r["w"])) for r in rows if r["w"] is not None]


def _weekly_metric(conn, user_id, table, expr, time_col, days) -> dict:
    rows = conn.execute(
        f"""SELECT strftime('%Y-%W', {time_col}) AS wk,
                   {expr} AS v
            FROM {table}
            WHERE user_id = ? AND {time_col} >= date('now', ?)
            GROUP BY wk""",
        (user_id, f"-{days} days"),
    ).fetchall()
    return {r["wk"]: (float(r["v"]) if r["v"] is not None else None) for r in rows}


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _p_value(r, n):
    """Two-sided p-value approximation via Fisher z-transform.

    Rough but fine for signalling significance in a UI. Real stats package
    would use scipy; we avoid the dep."""
    if n < 4 or r is None:
        return None
    r = max(min(r, 0.9999), -0.9999)
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    z_stat = abs(z / se)
    # Approximate normal-tail p (two-sided) using the survival-function shortcut
    p = math.erfc(z_stat / math.sqrt(2))
    return p


def _direction(metric_key: str, r: float) -> str:
    """Plain-english interpretation of the sign."""
    if r is None:
        return ""
    sign = "positive" if r > 0 else "negative"
    strength = ("negligible" if abs(r) < 0.1
                else "weak"     if abs(r) < 0.3
                else "moderate" if abs(r) < 0.5
                else "strong"   if abs(r) < 0.7
                else "very strong")
    hi_metric_hi_change = f"more {_METRIC_LABELS[metric_key]} → more weight gain"
    hi_metric_lo_change = f"more {_METRIC_LABELS[metric_key]} → more weight loss"
    if r > 0:
        return f"{strength} positive — {hi_metric_hi_change}"
    else:
        return f"{strength} negative — {hi_metric_lo_change}"
