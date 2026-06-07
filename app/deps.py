from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import Attendance, User

ADMIN_ROLES = {"commander", "executive_officer"}
CLAN_TZ = ZoneInfo("America/New_York")
RESET_HOUR = 7  # the clan-wars day rolls over at 7am clan time, not midnight


def current_clan_day() -> date:
    # shift back by the reset hour so the date only advances at 7am clan time
    return (datetime.now(CLAN_TZ) - timedelta(hours=RESET_HOUR)).date()


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id else None


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
