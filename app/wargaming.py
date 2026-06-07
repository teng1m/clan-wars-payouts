"""Thin wrapper around the Wargaming public WoT API.

All calls use the app's application_id only — no per-user access token needed
for the public clan endpoints we touch.
"""

import time

import httpx

from .config import WG_APPLICATION_ID

# default timeout caps every WG call so a slow/hung upstream can't pin
# threadpool slots and starve the rest of the app under partial outages
_client = httpx.Client(base_url="https://api.worldoftanks.com", timeout=10.0)

_current_season: dict | None = None
_season_fetched_at: float = 0.0
_SEASON_TTL = 86400  # 24h


def verify_access_token(access_token: str) -> tuple[int, str] | None:
    """Verify a login callback's access_token with WG and return the
    (account_id, nickname) pair WG ties to it, or None if the token is invalid.

    Never trust the account_id or nickname from the redirect URL — both are
    forgeable. prolongate rejects a token WG didn't issue, so a successful
    call proves ownership; we then look up the canonical nickname via
    account/info so a crafted ?nickname= can't set someone's display name.

    Endpoints:
      POST {BASE_URL}/wot/auth/prolongate/   — verify token, get account_id
      GET  {BASE_URL}/wot/account/info/      — fetch the nickname WG has on file
    """
    resp = _client.post(
        "/wot/auth/prolongate/",
        data={"application_id": WG_APPLICATION_ID, "access_token": access_token},
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "ok":
        return None
    account_id = payload["data"]["account_id"]

    info = _client.get(
        "/wot/account/info/",
        params={"application_id": WG_APPLICATION_ID, "account_id": account_id, "fields": "nickname"},
    )
    info.raise_for_status()
    nickname = info.json()["data"][str(account_id)]["nickname"]
    return account_id, nickname


def get_clan_membership(account_id: int) -> dict | None:
    """Return {"clan_id": int, "role": str} for the given account, or None
    if the player is not currently in a clan.

    Endpoint: GET {BASE_URL}/wot/clans/accountinfo/
    Params:   application_id, account_id, fields=clan_id,role
    Response: {"status": "ok", "data": {"<account_id>": {"clan_id": ..., "role": ...} | null}}
    """
    resp = _client.get(
        "/wot/clans/accountinfo/",
        params={"application_id": WG_APPLICATION_ID, "account_id": account_id, "fields": "clan.clan_id,role"},
    )
    resp.raise_for_status()
    data = resp.json()
    player_data = data["data"][str(account_id)]
    if player_data is None:
        return None
    return {"clan_id": player_data["clan"]["clan_id"], "role": player_data["role"]}


def get_clan_info(clan_id: int) -> dict | None:
    """Return the clan info dict for the given clan, or None if no such clan exists.

    Endpoint: GET {BASE_URL}/wot/clans/info/
    Params:   application_id, clan_id
    Response: {"status": "ok", "data": {"<clan_id>": {...clan fields...} | null}}
    """
    resp = _client.get(
        "/wot/clans/info/",
        params={"application_id": WG_APPLICATION_ID, "clan_id": clan_id, "fields": "tag"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["data"][str(clan_id)]


def get_current_season() -> dict | None:
    """Return the currently ACTIVE Global Map season, or — if none is active —
    the most recently FINISHED one. None only if the API returns no seasons at all.

    Cached in-process for 24h — season bounds change at most a few times a year,
    so refetching per request would just add latency.

    Endpoint: GET {BASE_URL}/wot/globalmap/seasons/
    Params:   application_id
    Response: {"status": "ok", "data": [{"status": "ACTIVE"|"FINISHED", "start": ..., "end": ..., "season_id": ..., ...}]}
    """
    global _current_season, _season_fetched_at
    if _current_season is None or time.time() - _season_fetched_at > _SEASON_TTL:
        resp = _client.get(
            "/wot/globalmap/seasons/",
            params={"application_id": WG_APPLICATION_ID},
        )
        resp.raise_for_status()
        seasons = resp.json()["data"]
        active = next((s for s in seasons if s["status"] == "ACTIVE"), None)
        if active is not None:
            _current_season = active
        else:
            finished = [s for s in seasons if s["status"] == "FINISHED"]
            _current_season = max(finished, key=lambda s: s["end"], default=None)
        _season_fetched_at = time.time()
    return _current_season
