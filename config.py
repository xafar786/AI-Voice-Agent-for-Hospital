import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/").strip()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "shifa_voice_ai").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip()
