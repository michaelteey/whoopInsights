"""Workouts-over-time analytics. Uses the workout-level data the API does
expose (sport_name, start_at, strain), not per-set data."""
from __future__ import annotations

import sqlite3


_KJ_TO_KCAL = 0.239006


def workout_summary_by_sport(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """One row per sport, ordered by most-recently-performed first.
    Includes session count, total calories, average duration, average strain.
    sport_ids is a comma-separated list of every sport_id we've seen for this
    sport_name — useful for verifying the API mapping (e.g., that Strength
    Trainer really is sport_id 123)."""
    rows = conn.execute(
        """
        SELECT sport_name,
               COUNT(*)                                                         AS session_count,
               MAX(start_at)                                                    AS last_at,
               MIN(start_at)                                                    AS first_at,
               AVG(strain)                                                      AS avg_strain,
               MAX(strain)                                                      AS max_strain,
               SUM(kilojoule)                                                   AS total_kj,
               AVG((julianday(end_at) - julianday(start_at)) * 24 * 60)         AS avg_minutes,
               SUM((julianday(end_at) - julianday(start_at)) * 24 * 60)         AS total_minutes,
               GROUP_CONCAT(DISTINCT sport_id)                                  AS sport_ids
        FROM workouts
        WHERE user_id = ?
        GROUP BY sport_name
        ORDER BY last_at DESC
        """,
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        kj = d.get("total_kj") or 0
        sessions = d.get("session_count") or 0
        total_kcal = round(kj * _KJ_TO_KCAL)
        total_minutes = round(d["total_minutes"]) if d["total_minutes"] else 0
        d["total_kcal"] = total_kcal
        d["avg_kcal"] = round(total_kcal / sessions) if sessions else 0
        d["avg_minutes"] = round(d["avg_minutes"]) if d["avg_minutes"] else 0
        d["total_minutes"] = total_minutes
        d["kcal_per_min"] = round(total_kcal / total_minutes, 1) if total_minutes else 0
        out.append(d)
    return out


def calories_by_sport(conn: sqlite3.Connection, user_id: int,
                      top_n: int = 12, by: str = "avg") -> list[dict]:
    """Calorie contributors per sport.

    by="avg":   sorts by average kcal per session (which sport burns the
                most per workout — the more useful "burner" view).
    by="total": sorts by total kcal across the lookback (reflects volume).
    """
    rows = conn.execute(
        """
        SELECT sport_name, SUM(kilojoule) AS total_kj, COUNT(*) AS sessions
        FROM workouts
        WHERE user_id = ? AND kilojoule IS NOT NULL
        GROUP BY sport_name
        """,
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        kj = r["total_kj"] or 0
        sessions = r["sessions"] or 1
        total = round(kj * _KJ_TO_KCAL)
        avg = round(total / sessions) if sessions else 0
        out.append({"sport_name": r["sport_name"], "kcal_total": total,
                    "kcal_avg": avg, "sessions": sessions})
    key = "kcal_avg" if by == "avg" else "kcal_total"
    out.sort(key=lambda d: d[key], reverse=True)
    return out[:top_n]


def sessions_for_sport(conn: sqlite3.Connection, user_id: int,
                       sport_name: str, limit: int = 200) -> list[dict]:
    """Most-recent N sessions of one sport."""
    rows = conn.execute(
        """
        SELECT id, sport_id, start_at, end_at, strain, avg_hr, max_hr, kilojoule
        FROM workouts
        WHERE user_id = ? AND LOWER(sport_name) = LOWER(?)
        ORDER BY start_at DESC
        LIMIT ?
        """,
        (user_id, sport_name, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def overall_time_summary(conn: sqlite3.Connection, user_id: int) -> dict:
    """Aggregate time stats across every sport: total minutes, total
    sessions, average session length."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS sessions,
               SUM((julianday(end_at) - julianday(start_at)) * 24 * 60) AS total_minutes,
               AVG((julianday(end_at) - julianday(start_at)) * 24 * 60) AS avg_minutes
        FROM workouts
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()
    sessions = row["sessions"] or 0
    total_minutes = round(row["total_minutes"] or 0)
    return {
        "sessions": sessions,
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 1),
        "avg_minutes": round(row["avg_minutes"]) if row["avg_minutes"] else 0,
    }


_BUCKET_FORMATS = {
    "day":   "%Y-%m-%d",
    "week":  "%Y-%W",
    "month": "%Y-%m",
}


def stacked_by_sport(conn: sqlite3.Connection, user_id: int,
                     bucket: str = "week",
                     days: int = 365,
                     top_n: int = 8) -> dict:
    """Stacked-by-sport count series for a given bucket size.

    bucket ∈ {'day', 'week', 'month'}. days = lookback window.
    Keeps the top_n most-frequent sports + 'other' so the legend stays sane.

    Output shape:
        {
            "labels": ["2025-44", "2025-45", ...],
            "datasets": [
                {"label": "weightlifting_msk", "data": [3, 2, 0, ...]},
                ...
            ]
        }
    """
    fmt = _BUCKET_FORMATS.get(bucket, _BUCKET_FORMATS["week"])
    rows = conn.execute(
        f"""
        SELECT strftime('{fmt}', start_at) AS bucket,
               sport_name,
               COUNT(*) AS n
        FROM workouts
        WHERE user_id = ? AND start_at >= date('now', ?)
        GROUP BY bucket, sport_name
        ORDER BY bucket ASC
        """,
        (user_id, f"-{days} days"),
    ).fetchall()

    if not rows:
        return {"labels": [], "datasets": []}

    buckets_seen: list[str] = []
    in_set: set[str] = set()
    sport_totals: dict[str, int] = {}
    cells: dict[tuple[str, str], int] = {}

    for r in rows:
        b = r["bucket"]
        sport = r["sport_name"] or "(unknown)"
        n = r["n"]
        if b not in in_set:
            in_set.add(b)
            buckets_seen.append(b)
        sport_totals[sport] = sport_totals.get(sport, 0) + n
        cells[(b, sport)] = n

    sorted_sports = sorted(sport_totals.items(), key=lambda kv: -kv[1])
    top_sports = [s for s, _ in sorted_sports[:top_n]]
    other_sports = [s for s, _ in sorted_sports[top_n:]]

    datasets = []
    for sport in top_sports:
        datasets.append({
            "label": sport,
            "data": [cells.get((b, sport), 0) for b in buckets_seen],
        })
    if other_sports:
        datasets.append({
            "label": "other",
            "data": [
                sum(cells.get((b, s), 0) for s in other_sports)
                for b in buckets_seen
            ],
        })
    return {"labels": buckets_seen, "datasets": datasets}


# Back-compat alias for old name. Routes will move to stacked_by_sport.
def weekly_stacked_by_sport(conn, user_id, weeks=52, top_n=8):
    return stacked_by_sport(conn, user_id, bucket="week", days=weeks * 7, top_n=top_n)


def weekly_session_counts(conn: sqlite3.Connection, user_id: int,
                          sport_name: str | None = None,
                          weeks: int = 52) -> list[dict]:
    """Count of sessions per ISO week. If sport_name is None, counts all sports."""
    if sport_name:
        sql = """
        SELECT strftime('%Y-%W', start_at) AS yw, COUNT(*) AS n
        FROM workouts
        WHERE user_id = ?
              AND LOWER(sport_name) = LOWER(?)
              AND start_at >= date('now', ?)
        GROUP BY yw
        ORDER BY yw ASC
        """
        rows = conn.execute(sql, (user_id, sport_name, f"-{weeks * 7} days")).fetchall()
    else:
        sql = """
        SELECT strftime('%Y-%W', start_at) AS yw, COUNT(*) AS n
        FROM workouts
        WHERE user_id = ?
              AND start_at >= date('now', ?)
        GROUP BY yw
        ORDER BY yw ASC
        """
        rows = conn.execute(sql, (user_id, f"-{weeks * 7} days")).fetchall()
    return [{"week": r["yw"], "value": r["n"]} for r in rows]
