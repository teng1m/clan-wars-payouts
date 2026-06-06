import random
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_URL, SECRET_KEY, WG_APPLICATION_ID
from app.db import engine, get_db
from app.deps import ADMIN_ROLES, get_current_user, require_admin
from app.models import AttendanceCode, Base, Clan, User
from app.wargaming import get_clan_info, get_clan_membership

CLAN_TZ = ZoneInfo("America/New_York")
RESET_HOUR = 7
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def expiry_for(attendance_date: date) -> datetime:
    # a day's code is valid until the next daily reset after its attendance date
    return datetime.combine(
        attendance_date + timedelta(days=1), time(hour=RESET_HOUR), tzinfo=CLAN_TZ
    )


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
def home(request: Request, user: User | None = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": user, "admin_roles": ADMIN_ROLES},
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


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


@app.get("/debug/users")
def list_users(db: Session = Depends(get_db)):
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [{"id": u.id, "wg_account_id": u.wg_account_id, "nickname": u.nickname} for u in users]


@app.get("/auth/callback")
def auth_callback(nickname, account_id, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
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
