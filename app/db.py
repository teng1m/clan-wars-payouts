from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DATABASE_URL

# check_same_thread is a sqlite-only knob; postgres connections are per-thread already.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

# pool_pre_ping issues a cheap SELECT 1 on checkout so we don't hand the app
# a connection the server has already closed. neon/managed postgres auto-
# suspends idle compute and our pooled sockets go stale; without this we'd
# 500 with AdminShutdown on the first request after a suspend.
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
