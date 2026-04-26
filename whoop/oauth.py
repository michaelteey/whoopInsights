import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

from config import Config


def build_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": Config.WHOOP_CLIENT_ID,
        "redirect_uri": Config.WHOOP_REDIRECT_URI,
        "scope": " ".join(Config.WHOOP_SCOPES),
        "state": state,
    }
    return f"{Config.WHOOP_AUTH_URL}?{urlencode(params)}"


def make_state() -> str:
    return secrets.token_urlsafe(24)


def exchange_code(code: str) -> dict:
    resp = requests.post(
        Config.WHOOP_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": Config.WHOOP_REDIRECT_URI,
            "client_id": Config.WHOOP_CLIENT_ID,
            "client_secret": Config.WHOOP_CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return _normalise_token(resp.json())


def refresh(refresh_token: str) -> dict:
    resp = requests.post(
        Config.WHOOP_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": Config.WHOOP_CLIENT_ID,
            "client_secret": Config.WHOOP_CLIENT_SECRET,
            "scope": " ".join(Config.WHOOP_SCOPES),
        },
        timeout=15,
    )
    resp.raise_for_status()
    return _normalise_token(resp.json())


def _normalise_token(payload: dict) -> dict:
    expires_in = int(payload.get("expires_in", 3600))
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 30)
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", ""),
        "expires_at": expires_at.isoformat(),
        "scope": payload.get("scope", ""),
    }
