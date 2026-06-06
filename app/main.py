import random
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .config import BASE_URL, SECRET_KEY, WG_APPLICATION_ID
from .db import engine, get_db
from .deps import (
    ADMIN_ROLES,
    CLAN_TZ,
    checked_in_today,
    get_current_user,
    require_admin,
    require_user,
)
from .models import Attendance, AttendanceCode, Base, Clan, User
from .wargaming import get_clan_info, get_clan_membership, verify_access_token

RESET_HOUR = 7
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def expiry_for(attendance_date: date) -> datetime:
    # a day's code is valid until the next daily reset after its attendance date
    return datetime.combine(attendance_date + timedelta(days=1), time(hour=RESET_HOUR), tzinfo=CLAN_TZ)


def get_or_create_todays_code(db: Session, clan_id: int) -> AttendanceCode:
    today = datetime.now(CLAN_TZ).date()
    stmt = select(AttendanceCode).where(
        AttendanceCode.clan_id == clan_id,
        AttendanceCode.attendance_date == today,
    )
    code = db.execute(stmt).scalar_one_or_none()
    if code is not None:
        return code

    code = AttendanceCode(
        clan_id=clan_id,
        code=generate_code(),
        attendance_date=today,
        expires_at=expiry_for(today),
    )
    db.add(code)
    try:
        db.commit()
    except IntegrityError:
        # another admin created today's code at the same moment; use theirs
        db.rollback()
        code = db.execute(stmt).scalar_one()
    return code


TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(403)
def forbidden(request: Request, exc: HTTPException):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"forbidden": exc.detail},
        status_code=403,
    )


@app.get("/", include_in_schema=False)
def home(
    request: Request,
    code: str = "",
    user: User | None = Depends(get_current_user),
    checked_in: bool = Depends(checked_in_today),
):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "admin_roles": ADMIN_ROLES,
            "checked_in": checked_in,
            "code": code,
            "error": None,
        },
    )


@app.get("/admin", include_in_schema=False)
def admin(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    code = get_or_create_todays_code(db, user.clan_id)
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"user": user, "code": code},
    )


@app.post("/", include_in_schema=False)
def check_in(
    request: Request,
    code: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    submitted = code.strip().upper()
    today = datetime.now(CLAN_TZ).date()

    error = None
    if user.clan_id is None:
        error = "You're not in a clan."
    else:
        matched = db.execute(
            select(AttendanceCode).where(
                AttendanceCode.clan_id == user.clan_id,
                AttendanceCode.attendance_date == today,
                AttendanceCode.code == submitted,
            )
        ).scalar_one_or_none()

        if matched is None:
            error = "That code isn't valid for today."
        else:
            db.add(
                Attendance(
                    clan_id=user.clan_id,
                    user_id=user.id,
                    attendance_date=today,
                    code_id=matched.id,
                )
            )
            try:
                db.commit()
            except IntegrityError:
                db.rollback()  # already checked in today — home will show that
            return RedirectResponse("/", status_code=303)

    # bad submission: nothing was written, so re-render home with the error inline
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "user": user,
            "admin_roles": ADMIN_ROLES,
            "checked_in": False,
            "code": submitted,
            "error": error,
        },
        status_code=400,
    )


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@app.get("/debug/users")
def list_users(db: Session = Depends(get_db)):
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [{"id": u.id, "wg_account_id": u.wg_account_id, "nickname": u.nickname} for u in users]


@app.get("/auth/callback")
def auth_callback(
    request: Request,
    status: str = "",
    access_token: str = "",
    nickname: str = "",
    db: Session = Depends(get_db),
) -> RedirectResponse:
    # never trust account_id from the URL: verify the token with WG and use the
    # account_id WG ties to it. status != ok or a bad token means reject.
    if status != "ok" or not access_token:
        return RedirectResponse("/", status_code=302)

    account_id = verify_access_token(access_token)
    if account_id is None:
        return RedirectResponse("/", status_code=302)

    existing = db.execute(select(User).where(User.wg_account_id == account_id)).scalar_one_or_none()

    if existing is None:
        user = User(wg_account_id=account_id, nickname=nickname)
        db.add(user)
    else:
        existing.nickname = nickname
        user = existing

    membership = get_clan_membership(account_id)
    if membership is None:
        user.clan_id = None
        user.clan_role = None
    else:
        clan = db.execute(select(Clan).where(Clan.wg_clan_id == membership["clan_id"])).scalar_one_or_none()

        if clan is None:
            clan_info = get_clan_info(membership["clan_id"])
            new_clan = Clan(wg_clan_id=membership["clan_id"], tag=clan_info["tag"], name=clan_info["name"])
            db.add(new_clan)
            db.flush()
            clan = new_clan

        user.clan_id = clan.id
        user.clan_role = membership["role"]

    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id

    return RedirectResponse(BASE_URL, status_code=302)


@app.get("/login")
def login() -> RedirectResponse:
    args = {"redirect_uri": f"{BASE_URL}/auth/callback", "application_id": WG_APPLICATION_ID}
    url = f"https://api.worldoftanks.com/wot/auth/login/?{urlencode(args)}"

    return RedirectResponse(url, status_code=302)


@app.get("/debug/seed")
def seed_user(db: Session = Depends(get_db)):
    user = User(
        wg_account_id=random.randint(1_000_000, 100_000_000),
        nickname=f"test_user_{random.randint(1000, 9999)}",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "wg_account_id": user.wg_account_id, "nickname": user.nickname}
