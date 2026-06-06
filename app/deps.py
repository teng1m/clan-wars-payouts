from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Attendance, User

ADMIN_ROLES = {"commander", "executive_officer"}
CLAN_TZ = ZoneInfo("America/New_York")


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
    today = datetime.now(CLAN_TZ).date()
    row = db.execute(
        select(Attendance).where(
            Attendance.user_id == user.id,
            Attendance.attendance_date == today,
        )
    ).scalar_one_or_none()
    return row is not None
