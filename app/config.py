import os

from dotenv import load_dotenv

load_dotenv()

WG_APPLICATION_ID = os.getenv("WG_APPLICATION_ID", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "")
