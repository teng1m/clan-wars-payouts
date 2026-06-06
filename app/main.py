import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib.parse import urlencode

from app.db import engine, get_db
from app.models import Base, User
from app.config import BASE_URL, WG_APPLICATION_ID


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/debug/users")
def list_users(db: Session = Depends(get_db)):
    users = db.execute(select(User).order_by(User.id)).scalars().all()
    return [
        {"id": u.id, "wg_account_id": u.wg_account_id, "nickname": u.nickname}
        for u in users
    ]
    
@app.get("/auth/callback")
def auth_callback(nickname, account_id, db: Session = Depends(get_db)) -> RedirectResponse:
    user = User(
        wg_account_id=account_id,
        nickname=nickname
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return FileResponse(STATIC_DIR / "success.html")
    # return RedirectResponse(BASE_URL, status_code=302)
    
    
    
@app.get("/login")
def login() -> RedirectResponse:
    args = {'redirect_uri': f'{BASE_URL}/auth/callback', 'application_id': WG_APPLICATION_ID}
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
