from flask import Blueprint, render_template, session, redirect, url_for, flash

from config import Config
from db import get_db
from analytics import body as analytics


bp = Blueprint("body", __name__, url_prefix="/body")


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
        "body_index.html",
        summary=analytics.summary(db, user_id),
        series=analytics.weight_series(db, user_id, days=365 * 3),
        correlations=analytics.correlations(db, user_id, lookback_days=365),
    )
