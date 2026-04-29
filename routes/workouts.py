from flask import Blueprint, render_template, session, redirect, url_for, flash

from config import Config
from db import get_db
from analytics import workouts as analytics


bp = Blueprint("workouts", __name__, url_prefix="/workouts")


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
    if not user_id:
        flash("Sign in with Whoop first.", "error")
        return redirect(url_for("dashboard.index"))
    db = get_db()
    sports        = analytics.workout_summary_by_sport(db, user_id)
    time_summary  = analytics.overall_time_summary(db, user_id)
    stacked_day   = analytics.stacked_by_sport(db, user_id, bucket="day",   days=180, top_n=8)
    stacked_week  = analytics.stacked_by_sport(db, user_id, bucket="week",  days=365, top_n=8)
    stacked_month = analytics.stacked_by_sport(db, user_id, bucket="month", days=365 * 3, top_n=8)
    kcal_avg      = analytics.calories_by_sport(db, user_id, top_n=12, by="avg")
    kcal_total    = analytics.calories_by_sport(db, user_id, top_n=12, by="total")
    return render_template("workouts_index.html",
                           sports=sports,
                           time_summary=time_summary,
                           stacked_day=stacked_day,
                           stacked_week=stacked_week,
                           stacked_month=stacked_month,
                           kcal=kcal_avg,
                           kcal_avg=kcal_avg,
                           kcal_total=kcal_total)


@bp.route("/<path:sport_name>")
def detail(sport_name: str):
    user_id = _current_user_id()
    if not user_id:
        flash("Sign in with Whoop first.", "error")
        return redirect(url_for("dashboard.index"))
    db = get_db()
    sessions = analytics.sessions_for_sport(db, user_id, sport_name)
    weekly = analytics.weekly_session_counts(db, user_id, sport_name=sport_name, weeks=104)
    return render_template("workouts_detail.html",
                           sport_name=sport_name,
                           sessions=sessions,
                           weekly=weekly)
