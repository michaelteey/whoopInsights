import time
from datetime import datetime, timezone
from typing import Iterator

import requests

from config import Config
from whoop import oauth


class WhoopClient:
    """Thin wrapper around the Whoop developer API.

    Auto-paginates list endpoints, auto-refreshes the access token, and
    backs off on 429 (rate limit) responses.
    """

    PAGE_LIMIT = 25  # Whoop's documented max is 25
    MAX_RETRIES = 5

    def __init__(self, access_token: str, refresh_token: str, expires_at: str,
                 on_token_refresh=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self._on_token_refresh = on_token_refresh

    def _ensure_fresh(self) -> None:
        if datetime.fromisoformat(self.expires_at) <= datetime.now(timezone.utc):
            new = oauth.refresh(self.refresh_token)
            self.access_token = new["access_token"]
            self.refresh_token = new["refresh_token"] or self.refresh_token
            self.expires_at = new["expires_at"]
            if self._on_token_refresh:
                self._on_token_refresh(new)

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._ensure_fresh()
        url = f"{Config.WHOOP_API_BASE}{path}"
        for attempt in range(self.MAX_RETRIES):
            resp = requests.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self.access_token}"},
                timeout=20,
            )
            if resp.status_code == 429:
                # Honour Retry-After if present, else exponential backoff capped at 30s.
                wait = float(resp.headers.get("Retry-After", min(2 ** attempt, 30)))
                time.sleep(wait)
                continue
            if 500 <= resp.status_code < 600 and attempt < self.MAX_RETRIES - 1:
                time.sleep(min(2 ** attempt, 10))
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, params: dict | None = None) -> Iterator[dict]:
        params = dict(params or {})
        params.setdefault("limit", self.PAGE_LIMIT)
        while True:
            page = self._get(path, params)
            for record in page.get("records", []):
                yield record
            next_token = page.get("next_token")
            if not next_token:
                return
            params["nextToken"] = next_token

    # ---- public endpoints ----

    # All endpoints are v2 — Whoop deprecated v1 in 09/2025.
    # /v1/cycle still resolves (likely redirected) but the other v1 paths
    # 404. Standardising on v2 across the board.

    def profile(self) -> dict:
        return self._get("/v2/user/profile/basic")

    def body_measurement(self) -> dict:
        return self._get("/v2/user/measurement/body")

    def cycles(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        yield from self._paginate("/v2/cycle", _range(start, end))

    def recoveries(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        yield from self._paginate("/v2/recovery", _range(start, end))

    def sleeps(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        yield from self._paginate("/v2/activity/sleep", _range(start, end))

    def workouts(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        yield from self._paginate("/v2/activity/workout", _range(start, end))


def _range(start: str | None, end: str | None) -> dict:
    params = {}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    return params
