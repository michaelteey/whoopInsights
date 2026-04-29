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
        d["total_kcal"] = round(kj * _KJ_TO_KCAL)
        d["avg_kcal"] = round((kj * _KJ_TO_KCAL) / sessions) if sessions else 0
        d["avg_minutes"] = round(d["avg_minutes"]) if d["avg_minutes"] else 0
        d["total_minutes"] = round(d["total_minutes"]) if d["total_minutes"] else 0
        out.append(d)
    return out


def calories_by_sport(conn: sqlite3.Connection, user_id: int,
                      top_n: int = 12) -> list[dict]:
    """Total kcal per sport, sorted descending. Top contributors first."""
    rows = conn.execute(
        """
        SELECT sport_name, SUM(kilojoule) AS total_kj, COUNT(*) AS sessions
        FROM workouts
        WHERE user_id = ? AND kilojoule IS NOT NULL
        GROUP BY sport_name
        ORDER BY total_kj DESC
        LIMIT ?
        """,
        (user_id, top_n),
    ).fetchall()
    return [
        {
            "sport_name": r["sport_name"],
            "kcal": round((r["total_kj"] or 0) * _KJ_TO_KCAL),
            "sessions": r["sessions"],
        }
        for r in rows
    ]


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


def weekly_stacked_by_sport(conn: sqlite3.Connection, user_id: int,
                            weeks: int = 52,
                            top_n: int = 8) -> dict:
    """Returns Chart.js-ready data for a stacked bar of weekly counts.

    Keeps the top_n most-frequent sports as their own datasets and rolls
    everything else into 'Other' so the chart legend stays readable.

    Output shape:
        {
            "labels": ["2025-44", "2025-45", ...],
            "datasets": [
                {"label": "Strength Trainer", "data": [3, 2, 0, ...]},
                {"label": "Running", "data": [...]},
                ...
            ]
        }
    """
    rows = conn.execute(
        """
        SELECT strftime('%Y-%W', start_at) AS yw,
               sport_name,
               COUNT(*) AS n
        FROM workouts
        WHERE user_id = ? AND start_at >= date('now', ?)
        GROUP BY yw, sport_name
        ORDER BY yw ASC
        """,
        (user_id, f"-{weeks * 7} days"),
    ).fetchall()

    if not rows:
        return {"labels": [], "datasets": []}

    weeks_set: list[str] = []
    seen_weeks = set()
    sport_totals: dict[str, int] = {}
    cells: dict[tuple[str, str], int] = {}

    for r in rows:
        yw = r["yw"]
        sport = r["sport_name"] or "(unknown)"
        n = r["n"]
        if yw not in seen_weeks:
            seen_weeks.add(yw)
            weeks_set.append(yw)
        sport_totals[sport] = sport_totals.get(sport, 0) + n
        cells[(yw, sport)] = n

    sorted_sports = sorted(sport_totals.items(), key=lambda kv: -kv[1])
    top_sports = [s for s, _ in sorted_sports[:top_n]]
    other_sports = [s for s, _ in sorted_sports[top_n:]]

    datasets = []
    for sport in top_sports:
        datasets.append({
            "label": sport,
            "data": [cells.get((yw, sport), 0) for yw in weeks_set],
        })
    if other_sports:
        datasets.append({
            "label": "Other",
            "data": [
                sum(cells.get((yw, s), 0) for s in other_sports)
                for yw in weeks_set
            ],
        })
    return {"labels": weeks_set, "datasets": datasets}


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
