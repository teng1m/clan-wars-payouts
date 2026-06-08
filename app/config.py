import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

WG_APPLICATION_ID = os.getenv("WG_APPLICATION_ID", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
BRAND_NAME = os.getenv("BRAND_NAME", "clantools.fyi")
SECRET_KEY = os.getenv("SECRET_KEY", "")

_PROJECT_ROOT = Path(__file__).parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_PROJECT_ROOT / 'clan_wars.db'}")

# hosts like Neon/Heroku/Fly hand out URLs starting with `postgres://` or
# `postgresql://`; SQLAlchemy needs the driver suffix to pick psycopg3.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# mark the session cookie Secure (HTTPS-only) whenever we're served over https;
# stays off for local http dev so the cookie still works there.
SECURE_COOKIES = BASE_URL.startswith("https://")
