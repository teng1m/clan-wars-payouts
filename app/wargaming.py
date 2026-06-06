"""Thin wrapper around the Wargaming public WoT API.

All calls use the app's application_id only — no per-user access token needed
for the public clan endpoints we touch.
"""

import httpx

from app.config import WG_APPLICATION_ID

BASE_URL = "https://api.worldoftanks.com"


def get_clan_membership(account_id: int) -> dict | None:
    """Return {"clan_id": int, "role": str} for the given account, or None
    if the player is not currently in a clan.

    Endpoint: GET {BASE_URL}/wot/clans/accountinfo/
    Params:   application_id, account_id, fields=clan_id,role
    Response: {"status": "ok", "data": {"<account_id>": {"clan_id": ..., "role": ...} | null}}
    """
    resp = httpx.get(
        f"{BASE_URL}/wot/clans/accountinfo/",
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
    resp = httpx.get(
        f"{BASE_URL}/wot/clans/info/",
        params={"application_id": WG_APPLICATION_ID, "clan_id": clan_id, "fields": "tag,name"},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["data"][str(clan_id)]
