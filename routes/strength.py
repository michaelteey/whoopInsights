from flask import Blueprint, render_template, session, redirect, url_for, flash, request

from config import Config
from db import get_db
from analytics import strength as strength_analytics


bp = Blueprint("strength", __name__, url_prefix="/strength")


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
    exercises = strength_analytics.list_exercises(db, user_id)
    return render_template("strength_index.html", exercises=exercises)


@bp.route("/<path:exercise_name>")
def detail(exercise_name: str):
    user_id = _current_user_id()
    if not user_id:
        flash("Sign in with Whoop first.", "error")
        return redirect(url_for("dashboard.index"))

    db = get_db()
    data = strength_analytics.progression(db, user_id, exercise_name)
    return render_template("strength_detail.html", **data)
