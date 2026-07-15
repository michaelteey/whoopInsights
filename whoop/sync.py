"""Pulls data from the Whoop API into SQLite.

Resilient by design:
- Splits the lookback window into 7-day chunks, syncs newest first.
- Each chunk is its own try/except — a failure in one chunk doesn't abort
  the whole sync. The user always gets *some* recent data.
- Each individual record insert is also wrapped — one bad row is logged and
  skipped rather than killing the chunk.
- Every chunk commits independently, so progress survives crashes.
- Idempotent: re-running picks up missing data without duplicating rows.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from db import dumps
from whoop.client import WhoopClient


log = logging.getLogger(__name__)

CHUNK_DAYS = 7


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def sync_user(conn: sqlite3.Connection, user_id: int, client: WhoopClient,
              lookback_days: int = 30) -> dict:
    """Non-streaming wrapper. Drains the iterator and returns final totals."""
    totals = {}
    for event in sync_user_iter(conn, user_id, client, lookback_days):
        if event["event"] == "complete":
            totals = event["totals"]
    return totals


def sync_user_iter(conn: sqlite3.Connection, user_id: int, client: WhoopClient,
                   lookback_days: int = 30):
    """Generator version: yields progress events as each chunk completes.

    Each yielded dict has an 'event' key:
      - 'start'        — begins, includes total_chunks
      - 'chunk_done'   — one chunk finished cleanly, includes running totals
      - 'chunk_failed' — chunk errored, others continue
      - 'complete'     — all chunks attempted, final totals included

    Newest-first chunked sync — same fault-tolerance as before, just
    observable in real time.
    """
    now = datetime.now(timezone.utc)
    totals = {"cycles": 0, "recoveries": 0, "sleeps": 0, "workouts": 0,
              "strength_sets": 0, "body_snapshots": 0,
              "chunks_ok": 0, "chunks_failed": 0,
              "errors": []}

    total_chunks = max(1, (lookback_days + CHUNK_DAYS - 1) // CHUNK_DAYS)
    yield {"event": "start", "lookback_days": lookback_days,
           "total_chunks": total_chunks}

    # Body measurement is a single "current" snapshot — pull once at start.
    try:
        if _snapshot_body_measurement(conn, user_id, client):
            totals["body_snapshots"] = 1
            conn.commit()
    except Exception:
        log.exception("Body measurement snapshot failed")

    chunk_index = 0
    for chunk_end_offset in range(0, lookback_days, CHUNK_DAYS):
        chunk_index += 1
        chunk_end = now - timedelta(days=chunk_end_offset)
        chunk_start = chunk_end - timedelta(days=CHUNK_DAYS)
        s, e = _iso(chunk_start), _iso(chunk_end)
        label = f"{chunk_start.date()}..{chunk_end.date()}"
        try:
            chunk_counts = _sync_chunk(conn, user_id, client, s, e)
            for k, v in chunk_counts.items():
                totals[k] = totals.get(k, 0) + v
            conn.commit()
            totals["chunks_ok"] += 1
            yield {"event": "chunk_done", "chunk": chunk_index,
                   "total_chunks": total_chunks, "label": label,
                   "chunk_counts": chunk_counts,
                   "totals": _public_totals(totals)}
        except Exception as exc:
            log.exception("Sync chunk %s failed", label)
            totals["chunks_failed"] += 1
            totals["errors"].append(f"{label}: {exc}")
            try:
                conn.rollback()
            except Exception:
                pass
            yield {"event": "chunk_failed", "chunk": chunk_index,
                   "total_chunks": total_chunks, "label": label,
                   "error": str(exc),
                   "totals": _public_totals(totals)}

    try:
        conn.execute(
            "UPDATE users SET last_synced_at = datetime('now') WHERE id = ?",
            (user_id,),
        )
        conn.commit()
    except Exception:
        log.exception("Failed to update last_synced_at")

    yield {"event": "complete", "totals": totals}


def _public_totals(totals: dict) -> dict:
    """Strip internal fields like the errors list for the streaming UI."""
    return {k: v for k, v in totals.items() if k != "errors"}


def _snapshot_body_measurement(conn, user_id, client) -> bool:
    """Fetch current body measurement and insert a row IF it differs from the
    most recent stored snapshot. Returns True when a new row was inserted.

    Body-fat isn't in the API today; we still write a column for it in case
    Whoop adds it later or we ingest from another source."""
    m = client.body_measurement()
    weight = m.get("weight_kilogram")
    height = m.get("height_meter")
    max_hr = m.get("max_heart_rate")
    body_fat = m.get("body_fat_percentage")  # present only if Whoop adds it

    if weight is None and height is None and body_fat is None:
        return False

    last = conn.execute(
        """SELECT weight_kg, height_m, max_hr, body_fat_pct
           FROM body_measurements
           WHERE user_id = ?
           ORDER BY recorded_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()

    if last and (last["weight_kg"] == weight
                 and last["height_m"] == height
                 and last["max_hr"] == max_hr
                 and last["body_fat_pct"] == body_fat):
        return False  # same as last snapshot — skip

    conn.execute(
        """INSERT INTO body_measurements (user_id, recorded_at, weight_kg,
                                          height_m, max_hr, body_fat_pct,
                                          source, raw)
           VALUES (?, datetime('now'), ?, ?, ?, ?, 'whoop', ?)""",
        (user_id, weight, height, max_hr, body_fat, dumps(m)),
    )
    return True


def _sync_chunk(conn, user_id, client, start, end) -> dict:
    """One 7-day window. Each entity is independently wrapped so a single
    bad endpoint doesn't kill the chunk."""
    counts = {"cycles": 0, "recoveries": 0, "sleeps": 0, "workouts": 0,
              "strength_sets": 0}
    counts["cycles"]    += _safe(_sync_cycles,    conn, user_id, client, start, end)
    counts["recoveries"]+= _safe(_sync_recoveries,conn, user_id, client, start, end)
    counts["sleeps"]    += _safe(_sync_sleeps,    conn, user_id, client, start, end)
    w, sets = _safe2(_sync_workouts,              conn, user_id, client, start, end)
    counts["workouts"]      += w
    counts["strength_sets"] += sets
    return counts


def _safe(fn, *args) -> int:
    try:
        return fn(*args)
    except Exception:
        log.exception("Entity sync failed in %s", fn.__name__)
        return 0


def _safe2(fn, *args) -> tuple[int, int]:
    try:
        return fn(*args)
    except Exception:
        log.exception("Entity sync failed in %s", fn.__name__)
        return (0, 0)


def _try_insert(conn, sql, params) -> int:
    """Run one upsert; swallow per-row errors so one bad row doesn't kill
    the whole entity loop. Returns 1 on success, 0 on failure."""
    try:
        conn.execute(sql, params)
        return 1
    except Exception:
        log.exception("Row insert failed; sql=%s", sql.strip().split()[0:3])
        return 0


def _sync_cycles(conn, user_id, client, start, end) -> int:
    n = 0
    for cycle in client.cycles(start=start, end=end):
        score = cycle.get("score") or {}
        n += _try_insert(
            conn,
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
    return n


def _sync_recoveries(conn, user_id, client, start, end) -> int:
    n = 0
    for recovery in client.recoveries(start=start, end=end):
        cycle_id = str(recovery.get("cycle_id"))
        if not cycle_id or cycle_id == "None":
            continue
        # If the cycle isn't already in our table, skip the recovery rather
        # than tripping the foreign-key constraint.
        exists = conn.execute(
            "SELECT 1 FROM cycles WHERE id = ?", (cycle_id,)
        ).fetchone()
        if not exists:
            continue
        rscore = recovery.get("score") or {}
        n += _try_insert(
            conn,
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
    return n


def _sync_sleeps(conn, user_id, client, start, end) -> int:
    n = 0
    for sleep in client.sleeps(start=start, end=end):
        score = sleep.get("score") or {}
        stage = score.get("stage_summary") or {}
        n += _try_insert(
            conn,
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
    return n


def _sync_workouts(conn, user_id, client, start, end) -> tuple[int, int]:
    n = 0
    sets_n = 0
    for workout in client.workouts(start=start, end=end):
        score = workout.get("score") or {}
        ok = _try_insert(
            conn,
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
        n += ok
        if ok:
            for s in _extract_strength_sets(workout):
                sets_n += _try_insert(
                    conn,
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
    return n, sets_n


def _extract_strength_sets(workout: dict) -> list[dict]:
    """Best-effort extraction of per-set strength data from a workout payload.

    Whoop's public API may or may not expose this. We probe a few likely shapes
    and return an empty list if none match.
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
