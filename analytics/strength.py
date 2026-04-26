"""Strength training progression analytics.

The headline feature: per-exercise weight/volume/e1RM curves and PRs over time.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime
from typing import Iterable


def epley_1rm(weight_kg: float, reps: int) -> float:
    """Epley formula. Caps at 10 reps (above that the estimate is unreliable)."""
    if weight_kg is None or reps is None or reps <= 0:
        return 0.0
    if reps == 1:
        return weight_kg
    return weight_kg * (1 + min(reps, 10) / 30)


def list_exercises(conn: sqlite3.Connection, user_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT exercise_name,
               COUNT(*)            AS set_count,
               MAX(performed_at)   AS last_performed,
               MAX(weight_kg)      AS heaviest_kg
        FROM strength_sets
        WHERE user_id = ?
        GROUP BY exercise_name
        ORDER BY last_performed DESC
        """,
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def progression(conn: sqlite3.Connection, user_id: int, exercise_name: str) -> dict:
    """Return everything the strength page needs for one exercise."""
    rows = conn.execute(
        """
        SELECT performed_at, reps, weight_kg, rpe
        FROM strength_sets
        WHERE user_id = ? AND exercise_name = ?
              AND weight_kg IS NOT NULL AND reps IS NOT NULL
        ORDER BY performed_at ASC
        """,
        (user_id, exercise_name),
    ).fetchall()
    sets = [dict(r) for r in rows]
    if not sets:
        return {"exercise": exercise_name, "sessions": [], "prs": [], "summary": {}}

    sessions = _aggregate_by_session(sets)
    prs = _detect_prs(sets)
    summary = _summary(sets, sessions)
    return {
        "exercise": exercise_name,
        "sessions": sessions,
        "prs": prs,
        "summary": summary,
    }


def _session_date(s: dict) -> str:
    return s["performed_at"][:10]


def _aggregate_by_session(sets: list[dict]) -> list[dict]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for s in sets:
        by_date[_session_date(s)].append(s)

    out = []
    for d in sorted(by_date.keys()):
        day_sets = by_date[d]
        top_weight = max((s["weight_kg"] for s in day_sets), default=0.0)
        top_e1rm = max((epley_1rm(s["weight_kg"], s["reps"]) for s in day_sets), default=0.0)
        volume = sum((s["weight_kg"] or 0) * (s["reps"] or 0) for s in day_sets)
        total_reps = sum(s["reps"] or 0 for s in day_sets)
        out.append({
            "date": d,
            "set_count": len(day_sets),
            "total_reps": total_reps,
            "top_weight_kg": round(top_weight, 2),
            "top_e1rm_kg": round(top_e1rm, 2),
            "volume_kg": round(volume, 2),
        })
    return out


def _detect_prs(sets: list[dict]) -> list[dict]:
    """Return the running list of PRs as they occur (e1RM-based)."""
    best = 0.0
    out = []
    for s in sets:
        e1rm = epley_1rm(s["weight_kg"], s["reps"])
        if e1rm > best + 0.001:
            best = e1rm
            out.append({
                "date": _session_date(s),
                "weight_kg": s["weight_kg"],
                "reps": s["reps"],
                "e1rm_kg": round(e1rm, 2),
            })
    return out


def _summary(sets: list[dict], sessions: list[dict]) -> dict:
    if not sets:
        return {}
    e1rms = [epley_1rm(s["weight_kg"], s["reps"]) for s in sets]
    return {
        "total_sessions": len(sessions),
        "total_sets": len(sets),
        "first_seen": sessions[0]["date"],
        "last_seen": sessions[-1]["date"],
        "best_weight_kg": round(max(s["weight_kg"] for s in sets), 2),
        "best_e1rm_kg": round(max(e1rms), 2),
        "current_e1rm_kg": round(sessions[-1]["top_e1rm_kg"], 2),
        "delta_e1rm_kg": round(sessions[-1]["top_e1rm_kg"] - sessions[0]["top_e1rm_kg"], 2),
    }
