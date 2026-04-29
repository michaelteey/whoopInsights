import json

from flask import (Blueprint, Response, render_template, session, redirect,
                   stream_with_context, url_for, flash, request)

from config import Config
from db import get_db
from analytics import trends, periods as periods_analytics
from whoop import oauth
from whoop.client import WhoopClient
from whoop.sync import sync_user, sync_user_iter


bp = Blueprint("dashboard", __name__)


def _current_user_id():
    user_id = session.get("user_id")
    if user_id is None and Config.USE_SAMPLE_DATA:
        row = get_db().execute(
            "SELECT id FROM users WHERE whoop_user_id = 'sample-user'"
        ).fetchone()
        if row:
            session["user_id"] = row["id"]
            return row["id"]
    return user_id


@bp.route("/")
def index():
    user_id = _current_user_id()
    db = get_db()

    user = None
    summary = None
    period_data = None
    if user_id:
        user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        summary = _user_summary(db, user_id)
        period_data = periods_analytics.period_summary(db, user_id)

    return render_template(
        "dashboard.html",
        user=user,
        summary=summary,
        period_data=period_data,
        has_credentials=Config.has_whoop_credentials(),
        sample_mode=Config.USE_SAMPLE_DATA,
    )


@bp.route("/trends")
def trends_view():
    user_id = _current_user_id()
    if not user_id:
        flash("Sign in with Whoop first.", "error")
        return redirect(url_for("dashboard.index"))

    days = int(request.args.get("days", 365))
    db = get_db()
    series = trends.daily_series(db, user_id, days)
    return render_template("trends.html", series=series, days=days)


@bp.route("/sync/stream")
def sync_stream():
    """Server-Sent Events: live progress as each chunk completes."""
    user_id = _current_user_id()
    if not user_id:
        return "Sign in first", 401

    db = get_db()
    tok = db.execute(
        "SELECT * FROM oauth_tokens WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not tok:
        return "No Whoop token", 400

    days = int(request.args.get("days", 30))

    def persist(new_token):
        db.execute(
            """UPDATE oauth_tokens
               SET access_token = ?, refresh_token = ?, expires_at = ?, scope = ?
               WHERE user_id = ?""",
            (new_token["access_token"],
             new_token["refresh_token"] or tok["refresh_token"],
             new_token["expires_at"],
             new_token.get("scope") or tok["scope"], user_id),
        )
        db.commit()

    client = WhoopClient(
        tok["access_token"], tok["refresh_token"], tok["expires_at"],
        on_token_refresh=persist,
    )

    @stream_with_context
    def events():
        try:
            for ev in sync_user_iter(db, user_id, client, lookback_days=days):
                yield f"data: {json.dumps(ev)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'event': 'fatal', 'error': str(exc)})}\n\n"

    return Response(events(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@bp.route("/sync", methods=["POST"])
def sync():
    user_id = _current_user_id()
    if not user_id:
        flash("Sign in with Whoop first.", "error")
        return redirect(url_for("dashboard.index"))

    db = get_db()
    tok = db.execute(
        "SELECT * FROM oauth_tokens WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not tok:
        flash("No Whoop token on file. Re-connect.", "error")
        return redirect(url_for("auth.login"))

    def persist(new_token):
        db.execute(
            """UPDATE oauth_tokens
               SET access_token = ?, refresh_token = ?, expires_at = ?, scope = ?
               WHERE user_id = ?""",
            (
                new_token["access_token"],
                new_token["refresh_token"] or tok["refresh_token"],
                new_token["expires_at"],
                new_token.get("scope") or tok["scope"],
                user_id,
            ),
        )
        db.commit()

    client = WhoopClient(
        tok["access_token"], tok["refresh_token"], tok["expires_at"],
        on_token_refresh=persist,
    )
    days = int(request.form.get("days", 30))
    counts = sync_user(db, user_id, client, lookback_days=days)

    msg = (
        f"Synced last {days} days: "
        f"{counts['cycles']} cycles, {counts['recoveries']} recoveries, "
        f"{counts['sleeps']} sleeps, {counts['workouts']} workouts, "
        f"{counts['strength_sets']} strength sets. "
        f"({counts['chunks_ok']} of {counts['chunks_ok'] + counts['chunks_failed']} weeks ok)"
    )
    if counts["chunks_failed"]:
        msg += f" Some weeks failed: {'; '.join(counts['errors'][:3])}"
        flash(msg, "error")
    else:
        flash(msg, "success")
    return redirect(url_for("dashboard.index"))


@bp.route("/debug/workouts")
def debug_workouts():
    """Inspect the raw JSON Whoop returned for your most recent workouts.

    Filters:
      ?sport=strength  -> Strength Trainer only (sport_id 123 OR matching name)
      ?sport=<name>    -> any sport_name match (case-insensitive substring)
    """
    user_id = _current_user_id()
    if not user_id:
        return "Sign in first", 401
    db = get_db()

    sport_filter = (request.args.get("sport") or "").strip().lower()
    if sport_filter == "strength":
        rows = db.execute(
            """SELECT id, sport_id, sport_name, start_at, raw
               FROM workouts
               WHERE user_id = ?
                 AND (sport_id = 123 OR LOWER(sport_name) LIKE '%strength%')
               ORDER BY start_at DESC LIMIT 10""",
            (user_id,),
        ).fetchall()
    elif sport_filter:
        rows = db.execute(
            """SELECT id, sport_id, sport_name, start_at, raw
               FROM workouts
               WHERE user_id = ? AND LOWER(sport_name) LIKE ?
               ORDER BY start_at DESC LIMIT 10""",
            (user_id, f"%{sport_filter}%"),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT id, sport_id, sport_name, start_at, raw
               FROM workouts WHERE user_id = ?
               ORDER BY start_at DESC LIMIT 10""",
            (user_id,),
        ).fetchall()

    sports_seen = db.execute(
        """SELECT sport_name, COUNT(*) AS n
           FROM workouts WHERE user_id = ?
           GROUP BY sport_name ORDER BY n DESC""",
        (user_id,),
    ).fetchall()

    return render_template(
        "debug_workouts.html",
        workouts=rows,
        sports_seen=sports_seen,
        active_filter=sport_filter,
    )


def _user_summary(db, user_id) -> dict:
    last_recovery = db.execute(
        """SELECT recovery_score, hrv_rmssd_milli, resting_heart_rate, recorded_at
           FROM recoveries WHERE user_id = ? ORDER BY recorded_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    last_cycle = db.execute(
        """SELECT strain, start_at FROM cycles WHERE user_id = ?
           ORDER BY start_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    last_sleep = db.execute(
        """SELECT sleep_performance_pct, start_at FROM sleeps
           WHERE user_id = ? AND nap = 0 ORDER BY start_at DESC LIMIT 1""",
        (user_id,),
    ).fetchone()
    workout_count = db.execute(
        "SELECT COUNT(*) AS n FROM workouts WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]
    set_count = db.execute(
        "SELECT COUNT(*) AS n FROM strength_sets WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]

    return {
        "recovery": dict(last_recovery) if last_recovery else None,
        "cycle": dict(last_cycle) if last_cycle else None,
        "sleep": dict(last_sleep) if last_sleep else None,
        "workout_count": workout_count,
        "set_count": set_count,
    }
