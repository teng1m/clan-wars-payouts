from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User

ADMIN_ROLES = {"commander", "executive_officer"}


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
