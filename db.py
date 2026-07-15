import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import g

from config import Config


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    whoop_user_id   TEXT UNIQUE,
    email           TEXT,
    first_name      TEXT,
    last_name       TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_synced_at  TEXT
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    access_token    TEXT NOT NULL,
    refresh_token   TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    scope           TEXT
);

CREATE TABLE IF NOT EXISTS cycles (
    id              TEXT PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_at        TEXT NOT NULL,
    end_at          TEXT,
    timezone_offset TEXT,
    strain          REAL,
    kilojoule       REAL,
    avg_hr          INTEGER,
    max_hr          INTEGER,
    raw             TEXT
);
CREATE INDEX IF NOT EXISTS idx_cycles_user_start ON cycles(user_id, start_at);

CREATE TABLE IF NOT EXISTS recoveries (
    cycle_id            TEXT PRIMARY KEY REFERENCES cycles(id) ON DELETE CASCADE,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recorded_at         TEXT NOT NULL,
    recovery_score      REAL,
    resting_heart_rate  REAL,
    hrv_rmssd_milli     REAL,
    spo2_percentage     REAL,
    skin_temp_celsius   REAL,
    raw                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_recoveries_user_at ON recoveries(user_id, recorded_at);

CREATE TABLE IF NOT EXISTS sleeps (
    id                          TEXT PRIMARY KEY,
    user_id                     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_at                    TEXT NOT NULL,
    end_at                      TEXT NOT NULL,
    nap                         INTEGER,
    sleep_performance_pct       REAL,
    sleep_efficiency_pct        REAL,
    sleep_consistency_pct       REAL,
    total_in_bed_milli          INTEGER,
    total_awake_milli           INTEGER,
    total_light_sleep_milli     INTEGER,
    total_slow_wave_sleep_milli INTEGER,
    total_rem_sleep_milli       INTEGER,
    respiratory_rate            REAL,
    raw                         TEXT
);
CREATE INDEX IF NOT EXISTS idx_sleeps_user_start ON sleeps(user_id, start_at);

CREATE TABLE IF NOT EXISTS workouts (
    id              TEXT PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    start_at        TEXT NOT NULL,
    end_at          TEXT NOT NULL,
    sport_id        INTEGER,
    sport_name      TEXT,
    strain          REAL,
    avg_hr          INTEGER,
    max_hr          INTEGER,
    kilojoule       REAL,
    distance_meter  REAL,
    raw             TEXT
);
CREATE INDEX IF NOT EXISTS idx_workouts_user_start ON workouts(user_id, start_at);
CREATE INDEX IF NOT EXISTS idx_workouts_sport ON workouts(user_id, sport_id, start_at);

-- Per-set lifts. Populated either from Whoop API (if/when exposed) or manual entry.
-- One row per set within a strength workout.
CREATE TABLE IF NOT EXISTS strength_sets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id      TEXT REFERENCES workouts(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    performed_at    TEXT NOT NULL,
    exercise_name   TEXT NOT NULL,
    set_index       INTEGER,
    reps            INTEGER,
    weight_kg       REAL,
    rpe             REAL,
    source          TEXT NOT NULL DEFAULT 'whoop',  -- whoop | manual | sample
    raw             TEXT
);
CREATE INDEX IF NOT EXISTS idx_sets_user_exercise_at ON strength_sets(user_id, exercise_name, performed_at);
CREATE INDEX IF NOT EXISTS idx_sets_workout ON strength_sets(workout_id);

-- Body composition snapshots. Whoop's /v2/user/measurement/body only returns
-- CURRENT values, so we snapshot on every sync (deduped on same-day same-values)
-- to build our own time series.
CREATE TABLE IF NOT EXISTS body_measurements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recorded_at     TEXT NOT NULL,
    weight_kg       REAL,
    height_m        REAL,
    max_hr          INTEGER,
    body_fat_pct    REAL,             -- nullable; not currently in Whoop's API
    source          TEXT NOT NULL DEFAULT 'whoop',
    raw             TEXT
);
CREATE INDEX IF NOT EXISTS idx_body_user_at ON body_measurements(user_id, recorded_at);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        Path(os.path.dirname(Config.DATABASE_PATH) or ".").mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(Config.DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exception=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    Path(os.path.dirname(Config.DATABASE_PATH) or ".").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


@contextmanager
def standalone_connection():
    """For scripts/CLI that don't run inside a Flask request."""
    Path(os.path.dirname(Config.DATABASE_PATH) or ".").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def dumps(value) -> str:
    return json.dumps(value, default=str)
