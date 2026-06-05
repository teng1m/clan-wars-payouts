import random
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.models import Base, User


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
    
# @app.get("/login")


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
