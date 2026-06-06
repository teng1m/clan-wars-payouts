import random
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_URL, SECRET_KEY, WG_APPLICATION_ID
from app.db import engine, get_db
from app.models import Base, Clan, User
from app.wargaming import get_clan_info, get_clan_membership

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


@app.get("/", include_in_schema=False)
def home(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    user = db.get(User, user_id) if user_id else None
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": user},
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
