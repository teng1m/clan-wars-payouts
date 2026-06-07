import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Attendance, Clan, User
from .wargaming import get_clan_info, get_clan_membership

ADMIN_ROLES = {"commander", "executive_officer"}
CLAN_TZ = ZoneInfo("America/New_York")
RESET_HOUR = 7  # the clan-wars day rolls over at 7am clan time, not midnight
SYNC_TTL = 300  # re-pull clan + role from WG at most once per 5 min per session


def current_clan_day() -> date:
    # shift back by the reset hour so the date only advances at 7am clan time
    return (datetime.now(CLAN_TZ) - timedelta(hours=RESET_HOUR)).date()


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def mark_session_synced(request: Request) -> None:
    """Stamp the session as freshly synced so get_current_user's TTL gate
    doesn't immediately re-pull on the next request."""
    request.session["synced_at"] = time.time()


def sync_clan_membership(user: User, db: Session) -> None:
    """Pull the user's current clan + role from WG and write them onto the User
    row. Creates a Clan record on the fly if WG reports a clan we haven't seen.
    Caller is responsible for committing."""
    membership = get_clan_membership(user.wg_account_id)
    if membership is None:
        user.clan_id = None
        user.clan_role = None
        return
    clan = db.execute(select(Clan).where(Clan.wg_clan_id == membership["clan_id"])).scalar_one_or_none()
    if clan is None:
        clan_info = get_clan_info(membership["clan_id"])
        clan = Clan(wg_clan_id=membership["clan_id"], tag=clan_info["tag"])
        db.add(clan)
        db.flush()
    user.clan_id = clan.id
    user.clan_role = membership["role"]


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None:
        return None

    # opportunistic refresh: if a user was demoted or kicked, this catches it
    # within SYNC_TTL of their next page load. session-scoped timestamp keeps
    # us from hammering WG on every request.
    if time.time() - request.session.get("synced_at", 0) > SYNC_TTL:
        try:
            sync_clan_membership(user, db)
            db.commit()
        except httpx.HTTPError:
            # WG is slow or down — keep serving with stale clan/role rather
            # than 500ing the request. we still bump synced_at below so we
            # don't retry on every single page hit during an outage.
            db.rollback()
        mark_session_synced(request)
    return user


def require_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.clan_role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="You need to be XO or higher to access this page.")
    return user


def checked_in_today(
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> bool:
    if user is None or user.clan_id is None:
        return False
    today = current_clan_day()
    row = db.execute(
        select(Attendance).where(
            Attendance.user_id == user.id,
            Attendance.attendance_date == today,
        )
    ).scalar_one_or_none()
    return row is not None
