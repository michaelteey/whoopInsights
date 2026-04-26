from datetime import datetime, timezone
from typing import Iterator

import requests

from config import Config
from whoop import oauth


class WhoopClient:
    """Thin wrapper around the Whoop developer API.

    Pages through list endpoints automatically. Refreshes the access token
    in-place when it expires.
    """

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
        resp = requests.get(
            f"{Config.WHOOP_API_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, path: str, params: dict | None = None) -> Iterator[dict]:
        params = dict(params or {})
        params.setdefault("limit", 25)
        while True:
            page = self._get(path, params)
            for record in page.get("records", []):
                yield record
            next_token = page.get("next_token")
            if not next_token:
                return
            params["nextToken"] = next_token

    def profile(self) -> dict:
        return self._get("/v1/user/profile/basic")

    def cycles(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        yield from self._paginate("/v1/cycle", params)

    def recovery_for_cycle(self, cycle_id: str) -> dict | None:
        try:
            return self._get(f"/v1/cycle/{cycle_id}/recovery")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    def sleeps(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        yield from self._paginate("/v1/activity/sleep", params)

    def workouts(self, start: str | None = None, end: str | None = None) -> Iterator[dict]:
        params = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        yield from self._paginate("/v1/activity/workout", params)
