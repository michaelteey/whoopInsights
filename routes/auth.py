from flask import Blueprint, redirect, request, session, url_for, flash, current_app

from config import Config
from db import get_db
from whoop import oauth
from whoop.client import WhoopClient


bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login")
def login():
    if not Config.has_whoop_credentials():
        flash("Whoop API credentials not set. Add WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET to .env.", "error")
        return redirect(url_for("dashboard.index"))
    state = oauth.make_state()
    session["oauth_state"] = state
    return redirect(oauth.build_authorize_url(state))


@bp.route("/callback")
def callback():
    state = request.args.get("state")
    if not state or state != session.pop("oauth_state", None):
        flash("OAuth state mismatch — try again.", "error")
        return redirect(url_for("dashboard.index"))

    error = request.args.get("error")
    if error:
        flash(f"Whoop returned an error: {error}", "error")
        return redirect(url_for("dashboard.index"))

    code = request.args.get("code")
    if not code:
        flash("Missing authorisation code.", "error")
        return redirect(url_for("dashboard.index"))

    token = oauth.exchange_code(code)
    client = WhoopClient(token["access_token"], token["refresh_token"], token["expires_at"])
    profile = client.profile()

    db = get_db()
    cur = db.execute(
        """
        INSERT INTO users (whoop_user_id, email, first_name, last_name)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(whoop_user_id) DO UPDATE SET
            email = excluded.email,
            first_name = excluded.first_name,
            last_name = excluded.last_name
        RETURNING id
        """,
        (
            str(profile.get("user_id")),
            profile.get("email"),
            profile.get("first_name"),
            profile.get("last_name"),
        ),
    )
    user_id = cur.fetchone()["id"]
    db.execute(
        """
        INSERT INTO oauth_tokens (user_id, access_token, refresh_token, expires_at, scope)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            expires_at = excluded.expires_at,
            scope = excluded.scope
        """,
        (user_id, token["access_token"], token["refresh_token"], token["expires_at"], token.get("scope")),
    )
    db.commit()
    session["user_id"] = user_id
    flash("Connected to Whoop. Run a sync from the dashboard to pull your data.", "success")
    return redirect(url_for("dashboard.index"))


@bp.route("/logout")
def logout():
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("dashboard.index"))
