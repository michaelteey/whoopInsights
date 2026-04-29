from flask import Blueprint, render_template, session, redirect, url_for, flash

from config import Config
from db import get_db
from analytics import sleep as analytics


bp = Blueprint("sleep", __name__, url_prefix="/sleep")


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
    return render_template(
        "sleep_index.html",
        overview=analytics.overview(db, user_id),
        debt_curve=analytics.debt_curve(db, user_id, days=60),
        stage_day=analytics.stage_stacked(db, user_id, bucket="day", days=60),
        stage_week=analytics.stage_stacked(db, user_id, bucket="week", days=365),
        stage_month=analytics.stage_stacked(db, user_id, bucket="month", days=365 * 3),
        disturbances=analytics.disturbances_trend(db, user_id, days=90),
        wd_we=analytics.weekday_vs_weekend(db, user_id, days=90),
    )
