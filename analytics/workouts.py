"""Workouts-over-time analytics. Uses the workout-level data the API does
expose (sport_name, start_at, strain), not per-set data."""
from __future__ import annotations

import sqlite3


def workout_summary_by_sport(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    """One row per sport, ordered by most-recently-performed first."""
    rows = conn.execute(
        """
        SELECT sport_name,
               COUNT(*)                AS session_count,
               MAX(start_at)           AS last_at,
               MIN(start_at)           AS first_at,
               AVG(strain)             AS avg_strain,
               MAX(strain)             AS max_strain,
               SUM(
                   CAST(
                       (julianday(end_at) - julianday(start_at)) * 24 * 60
                   AS INTEGER)
               )                       AS total_minutes
        FROM workouts
        WHERE user_id = ?
        GROUP BY sport_name
        ORDER BY last_at DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def sessions_for_sport(conn: sqlite3.Connection, user_id: int,
                       sport_name: str, limit: int = 200) -> list[dict]:
    """Most-recent N sessions of one sport."""
    rows = conn.execute(
        """
        SELECT id, start_at, end_at, strain, avg_hr, max_hr, kilojoule
        FROM workouts
        WHERE user_id = ? AND LOWER(sport_name) = LOWER(?)
        ORDER BY start_at DESC
        LIMIT ?
        """,
        (user_id, sport_name, limit),
    ).fetchall()
    return [dict(r) for r in rows]


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
