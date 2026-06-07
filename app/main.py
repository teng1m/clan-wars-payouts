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

from .config import BASE_URL, SECRET_KEY, SECURE_COOKIES, WG_APPLICATION_ID
from .db import engine, get_db
from .deps import (
    ADMIN_ROLES,
    CLAN_TZ,
    RESET_HOUR,
    checked_in_today,
    current_clan_day,
    get_current_user,
    monday_of,
    require_admin,
    require_user,
)
from .models import Attendance, AttendanceCode, Base, Clan, User
from .wargaming import get_clan_info, get_clan_membership, verify_access_token

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def expiry_for(attendance_date: date) -> datetime:
    # a day's code is valid until the next daily reset after its attendance date
    return datetime.combine(attendance_date + timedelta(days=1), time(hour=RESET_HOUR), tzinfo=CLAN_TZ)


def get_or_create_todays_code(db: Session, clan_id: int) -> AttendanceCode:
    today = current_clan_day()
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
templates.env.globals["admin_roles"] = ADMIN_ROLES


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=SECURE_COOKIES,
    same_site="lax",
)

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
        name="home.html",
        context={
            "user": user,
            "admin_roles": ADMIN_ROLES,
            "checked_in": checked_in,
            "code": code,
            "error": None,
            "clan_day": current_clan_day(),
        },
    )


@app.get("/admin", include_in_schema=False)
def admin(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    code = get_or_create_todays_code(db, user.clan_id)

    dates = db.execute(
        select(Attendance.attendance_date)
        .where(Attendance.clan_id == user.clan_id)
        .distinct()
    ).scalars().all()
    mondays = sorted({monday_of(d) for d in dates}, reverse=True)
    weeks = [{"start": m, "end": m + timedelta(days=6)} for m in mondays]

    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"user": user, "code": code, "weeks": weeks},
    )


@app.get("/payouts", include_in_schema=False)
def payouts_sheet(
    request: Request,
    week: date | None = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if week is None:
        return RedirectResponse("/admin", status_code=302)
    week_start = monday_of(week)  # defensive: snap any day to that week's Monday
    days = [week_start + timedelta(days=i) for i in range(7)]
    week_end = days[-1]

    flat = db.execute(
        select(User.nickname, Attendance.user_id, Attendance.attendance_date)
        .join(User, User.id == Attendance.user_id)
        .where(
            Attendance.clan_id == user.clan_id,
            Attendance.attendance_date >= week_start,
            Attendance.attendance_date < week_start + timedelta(days=7),
        )
    ).all()

    by_user: dict[int, dict] = {}
    for nickname, user_id, attendance_date in flat:
        bucket = by_user.setdefault(user_id, {"nickname": nickname, "days_set": set()})
        bucket["days_set"].add(attendance_date)

    rows = sorted(
        by_user.values(),
        key=lambda r: (-len(r["days_set"]), r["nickname"].lower()),
    )

    return templates.TemplateResponse(
        request=request,
        name="payouts.html",
        context={"user": user, "week_start": week_start, "week_end": week_end, "days": days, "rows": rows},
    )


@app.post("/", include_in_schema=False)
def check_in(
    request: Request,
    code: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    submitted = code.strip().upper()
    today = current_clan_day()

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
        name="home.html",
        context={
            "user": user,
            "admin_roles": ADMIN_ROLES,
            "checked_in": False,
            "code": submitted,
            "error": error,
            "clan_day": today,
        },
        status_code=400,
    )


@app.post("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


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
            new_clan = Clan(wg_clan_id=membership["clan_id"], tag=clan_info["tag"])
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
