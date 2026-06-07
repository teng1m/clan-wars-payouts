from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DATABASE_URL

# check_same_thread is a sqlite-only knob; postgres connections are per-thread already.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
