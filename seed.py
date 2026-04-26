"""Generates plausible sample data so the app demos without Whoop credentials.

Creates one user, ~120 days of cycles/recoveries/sleeps, and a strength training
history across squat, bench, deadlift, and overhead press with realistic
progression and noise.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from db import dumps, standalone_connection


SAMPLE_USER = ("sample-user", "demo@example.com", "Demo", "User")


def seed_if_empty() -> None:
    with standalone_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE whoop_user_id = ?", (SAMPLE_USER[0],)).fetchone()
        if existing:
            return
        random.seed(42)
        cur = conn.execute(
            "INSERT INTO users (whoop_user_id, email, first_name, last_name) VALUES (?,?,?,?) RETURNING id",
            SAMPLE_USER,
        )
        user_id = cur.fetchone()[0]
        _seed_cycles_and_recovery(conn, user_id, days=180)
        _seed_sleeps(conn, user_id, days=180)
        _seed_strength(conn, user_id, weeks=24)


def _seed_cycles_and_recovery(conn, user_id, days):
    end = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0)
    for i in range(days):
        start = end - timedelta(days=days - i)
        cycle_id = f"sample-cycle-{i}"
        strain = max(2.5, min(20.0, 8 + 4 * math.sin(i / 6) + random.gauss(0, 2)))
        conn.execute(
            """INSERT INTO cycles (id, user_id, start_at, end_at, timezone_offset,
                                  strain, kilojoule, avg_hr, max_hr, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (cycle_id, user_id, start.isoformat(), (start + timedelta(days=1)).isoformat(),
             "+00:00", strain, 6000 + random.randint(-2000, 2000),
             65 + random.randint(-5, 10), 145 + random.randint(-10, 15), dumps({"sample": True})),
        )
        recovery_score = max(15, min(99,
            70 - 0.6 * (strain - 8) + 5 * math.sin(i / 14) + random.gauss(0, 8)))
        hrv = max(20, 65 + 0.3 * (recovery_score - 70) + random.gauss(0, 6))
        rhr = 56 - 0.1 * (recovery_score - 70) + random.gauss(0, 2)
        conn.execute(
            """INSERT INTO recoveries (cycle_id, user_id, recorded_at, recovery_score,
                                       resting_heart_rate, hrv_rmssd_milli,
                                       spo2_percentage, skin_temp_celsius, raw)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (cycle_id, user_id, start.isoformat(), recovery_score, rhr, hrv,
             96 + random.uniform(-1, 1.5), 33.5 + random.gauss(0, 0.4), dumps({"sample": True})),
        )


def _seed_sleeps(conn, user_id, days):
    end = datetime.now(timezone.utc).replace(hour=6, minute=0, second=0, microsecond=0)
    for i in range(days):
        wake = end - timedelta(days=days - i - 1)
        bed = wake - timedelta(hours=8) - timedelta(minutes=random.randint(-45, 30))
        in_bed = (wake - bed).total_seconds() * 1000
        awake = random.randint(10, 40) * 60 * 1000
        rem = int(0.22 * (in_bed - awake))
        sws = int(0.18 * (in_bed - awake))
        light = int(in_bed - awake - rem - sws)
        perf = max(50, min(100, 90 + random.gauss(0, 8)))
        conn.execute(
            """INSERT INTO sleeps (id, user_id, start_at, end_at, nap,
                                   sleep_performance_pct, sleep_efficiency_pct, sleep_consistency_pct,
                                   total_in_bed_milli, total_awake_milli, total_light_sleep_milli,
                                   total_slow_wave_sleep_milli, total_rem_sleep_milli,
                                   respiratory_rate, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"sample-sleep-{i}", user_id, bed.isoformat(), wake.isoformat(), 0,
             perf, max(70, perf - 5), max(50, 80 + random.gauss(0, 8)),
             int(in_bed), awake, light, sws, rem,
             15 + random.gauss(0, 0.6), dumps({"sample": True})),
        )


def _seed_strength(conn, user_id, weeks):
    """Two strength sessions per week with realistic progression."""
    exercises = {
        "Back Squat":      {"start_kg": 80,  "weekly_gain": 1.25, "rep_range": (3, 6)},
        "Bench Press":     {"start_kg": 60,  "weekly_gain": 0.8,  "rep_range": (4, 8)},
        "Deadlift":        {"start_kg": 100, "weekly_gain": 1.5,  "rep_range": (3, 5)},
        "Overhead Press":  {"start_kg": 40,  "weekly_gain": 0.5,  "rep_range": (5, 8)},
    }
    sessions_per_week = 2
    end = datetime.now(timezone.utc).replace(hour=18, minute=0, second=0, microsecond=0)

    for w in range(weeks):
        week_start = end - timedelta(weeks=weeks - w)
        for s in range(sessions_per_week):
            session_at = week_start + timedelta(days=s * 3 + 1)
            workout_id = f"sample-workout-{w}-{s}"
            conn.execute(
                """INSERT INTO workouts (id, user_id, start_at, end_at, sport_id, sport_name,
                                         strain, avg_hr, max_hr, kilojoule, distance_meter, raw)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (workout_id, user_id, session_at.isoformat(),
                 (session_at + timedelta(minutes=70)).isoformat(),
                 45, "Strength Trainer",
                 8 + random.uniform(-1, 2), 120, 165, 1500, 0,
                 dumps({"sample": True})),
            )
            for ex_name, cfg in exercises.items():
                target = cfg["start_kg"] + cfg["weekly_gain"] * w
                target += random.gauss(0, cfg["weekly_gain"] * 0.6)
                # Round to nearest 2.5 kg
                top = round(target / 2.5) * 2.5
                # Five working sets: warmup ramp + 3 working sets
                ramp = [round((top * 0.6) / 2.5) * 2.5, round((top * 0.8) / 2.5) * 2.5, top, top, top]
                rep_lo, rep_hi = cfg["rep_range"]
                for set_index, weight in enumerate(ramp):
                    reps = random.randint(rep_lo, rep_hi)
                    if set_index < 2:
                        reps = max(reps, 5)
                    conn.execute(
                        """INSERT INTO strength_sets (workout_id, user_id, performed_at,
                                                     exercise_name, set_index, reps,
                                                     weight_kg, rpe, source, raw)
                           VALUES (?,?,?,?,?,?,?,?, 'sample', ?)""",
                        (workout_id, user_id,
                         (session_at + timedelta(minutes=set_index * 4)).isoformat(),
                         ex_name, set_index, reps, weight,
                         6 + (set_index * 0.5) + random.uniform(-0.5, 0.5),
                         dumps({"sample": True})),
                    )


if __name__ == "__main__":
    seed_if_empty()
    print("Sample data seeded (or already present).")
