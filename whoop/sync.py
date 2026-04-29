"""Pulls data from the Whoop API into SQLite.

Designed to be safe to run repeatedly: every upsert is idempotent.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from db import dumps
from whoop.client import WhoopClient


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def sync_user(conn: sqlite3.Connection, user_id: int, client: WhoopClient,
              lookback_days: int = 365) -> dict:
    """Pull recent data for one user. Returns counts per entity.

    Each list endpoint paginates server-side at 25 records/page. For a year
    of data that's roughly 60 total HTTP calls, well under Whoop's 100/min
    rate limit. The client retries on 429 just in case.
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    s, e = _iso(start), _iso(end)
    counts = {
        "cycles": _sync_cycles(conn, user_id, client, s, e),
        "recoveries": _sync_recoveries(conn, user_id, client, s, e),
        "sleeps": _sync_sleeps(conn, user_id, client, s, e),
        "workouts": _sync_workouts(conn, user_id, client, s, e),
    }
    conn.execute(
        "UPDATE users SET last_synced_at = datetime('now') WHERE id = ?",
        (user_id,),
    )
    conn.commit()
    return counts


def _sync_cycles(conn, user_id, client, start, end) -> int:
    n = 0
    for cycle in client.cycles(start=start, end=end):
        score = cycle.get("score") or {}
        conn.execute(
            """
            INSERT INTO cycles (id, user_id, start_at, end_at, timezone_offset,
                                strain, kilojoule, avg_hr, max_hr, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                end_at = excluded.end_at,
                strain = excluded.strain,
                kilojoule = excluded.kilojoule,
                avg_hr = excluded.avg_hr,
                max_hr = excluded.max_hr,
                raw = excluded.raw
            """,
            (
                str(cycle["id"]),
                user_id,
                cycle.get("start"),
                cycle.get("end"),
                cycle.get("timezone_offset"),
                score.get("strain"),
                score.get("kilojoule"),
                score.get("average_heart_rate"),
                score.get("max_heart_rate"),
                dumps(cycle),
            ),
        )
        n += 1
    return n


def _sync_recoveries(conn, user_id, client, start, end) -> int:
    """Pulls recoveries via the list endpoint — one paginated stream rather
    than one HTTP call per cycle."""
    n = 0
    for recovery in client.recoveries(start=start, end=end):
        cycle_id = str(recovery.get("cycle_id"))
        if not cycle_id or cycle_id == "None":
            continue
        rscore = recovery.get("score") or {}
        conn.execute(
            """
            INSERT INTO recoveries (cycle_id, user_id, recorded_at, recovery_score,
                                    resting_heart_rate, hrv_rmssd_milli,
                                    spo2_percentage, skin_temp_celsius, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cycle_id) DO UPDATE SET
                recovery_score = excluded.recovery_score,
                resting_heart_rate = excluded.resting_heart_rate,
                hrv_rmssd_milli = excluded.hrv_rmssd_milli,
                spo2_percentage = excluded.spo2_percentage,
                skin_temp_celsius = excluded.skin_temp_celsius,
                raw = excluded.raw
            """,
            (
                cycle_id,
                user_id,
                recovery.get("created_at") or recovery.get("updated_at"),
                rscore.get("recovery_score"),
                rscore.get("resting_heart_rate"),
                rscore.get("hrv_rmssd_milli"),
                rscore.get("spo2_percentage"),
                rscore.get("skin_temp_celsius"),
                dumps(recovery),
            ),
        )
        n += 1
    return n


def _sync_sleeps(conn, user_id, client, start, end) -> int:
    n = 0
    for sleep in client.sleeps(start=start, end=end):
        score = sleep.get("score") or {}
        stage = score.get("stage_summary") or {}
        conn.execute(
            """
            INSERT INTO sleeps (id, user_id, start_at, end_at, nap,
                                sleep_performance_pct, sleep_efficiency_pct,
                                sleep_consistency_pct, total_in_bed_milli,
                                total_awake_milli, total_light_sleep_milli,
                                total_slow_wave_sleep_milli, total_rem_sleep_milli,
                                respiratory_rate, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                sleep_performance_pct = excluded.sleep_performance_pct,
                sleep_efficiency_pct = excluded.sleep_efficiency_pct,
                sleep_consistency_pct = excluded.sleep_consistency_pct,
                raw = excluded.raw
            """,
            (
                str(sleep["id"]),
                user_id,
                sleep.get("start"),
                sleep.get("end"),
                1 if sleep.get("nap") else 0,
                score.get("sleep_performance_percentage"),
                score.get("sleep_efficiency_percentage"),
                score.get("sleep_consistency_percentage"),
                stage.get("total_in_bed_time_milli"),
                stage.get("total_awake_time_milli"),
                stage.get("total_light_sleep_time_milli"),
                stage.get("total_slow_wave_sleep_time_milli"),
                stage.get("total_rem_sleep_time_milli"),
                score.get("respiratory_rate"),
                dumps(sleep),
            ),
        )
        n += 1
    return n


def _sync_workouts(conn, user_id, client, start, end) -> int:
    n = 0
    for workout in client.workouts(start=start, end=end):
        score = workout.get("score") or {}
        conn.execute(
            """
            INSERT INTO workouts (id, user_id, start_at, end_at, sport_id, sport_name,
                                  strain, avg_hr, max_hr, kilojoule, distance_meter, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                strain = excluded.strain,
                avg_hr = excluded.avg_hr,
                max_hr = excluded.max_hr,
                kilojoule = excluded.kilojoule,
                distance_meter = excluded.distance_meter,
                raw = excluded.raw
            """,
            (
                str(workout["id"]),
                user_id,
                workout.get("start"),
                workout.get("end"),
                workout.get("sport_id"),
                workout.get("sport_name"),
                score.get("strain"),
                score.get("average_heart_rate"),
                score.get("max_heart_rate"),
                score.get("kilojoule"),
                score.get("distance_meter"),
                dumps(workout),
            ),
        )
        # If the API returns per-set strength data, capture it. Field names here
        # are speculative and will be confirmed against a real response.
        for s in _extract_strength_sets(workout):
            conn.execute(
                """
                INSERT INTO strength_sets (workout_id, user_id, performed_at,
                                           exercise_name, set_index, reps,
                                           weight_kg, rpe, source, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'whoop', ?)
                """,
                (
                    str(workout["id"]),
                    user_id,
                    s["performed_at"],
                    s["exercise_name"],
                    s.get("set_index"),
                    s.get("reps"),
                    s.get("weight_kg"),
                    s.get("rpe"),
                    dumps(s),
                ),
            )
        n += 1
    return n


def _extract_strength_sets(workout: dict) -> list[dict]:
    """Best-effort extraction of per-set strength data from a workout payload.

    Whoop's public API may or may not expose this. We probe a few likely shapes
    and return an empty list if none match. Confirm against a real response and
    tighten this once the schema is known.
    """
    candidates = (
        workout.get("strength_trainer")
        or workout.get("strength")
        or workout.get("exercises")
        or []
    )
    out: list[dict] = []
    if not isinstance(candidates, list):
        return out
    workout_start = workout.get("start")
    for ex in candidates:
        name = ex.get("name") or ex.get("exercise_name")
        sets = ex.get("sets") or []
        for i, s in enumerate(sets):
            out.append({
                "performed_at": s.get("performed_at") or workout_start,
                "exercise_name": name or "Unknown",
                "set_index": s.get("index", i),
                "reps": s.get("reps"),
                "weight_kg": s.get("weight_kg") or s.get("weight"),
                "rpe": s.get("rpe"),
            })
    return out
