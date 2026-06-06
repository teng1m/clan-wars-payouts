import os

from dotenv import load_dotenv

load_dotenv()

WG_APPLICATION_ID = os.getenv("WG_APPLICATION_ID", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "")

# mark the session cookie Secure (HTTPS-only) whenever we're served over https;
# stays off for local http dev so the cookie still works there.
SECURE_COOKIES = BASE_URL.startswith("https://")
