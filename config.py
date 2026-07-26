import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/").strip()
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "shifa_voice_ai").strip()
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").strip()
ADMIN_SIGNUP_CODE = os.getenv("ADMIN_SIGNUP_CODE", "8754").strip()

ASR_MODEL_DIR = os.getenv("ASR_MODEL_DIR", str(BASE_DIR / "ASR")).strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano").strip()
OPENAI_CLASSIFIER_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_CLASSIFIER_MAX_OUTPUT_TOKENS", "1024"))
OPENAI_REPLY_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_REPLY_MAX_OUTPUT_TOKENS", "1024"))
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts").strip()
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "cedar").strip()
OPENAI_TTS_RESPONSE_FORMAT = os.getenv("OPENAI_TTS_RESPONSE_FORMAT", "mp3").strip()
OPENAI_TTS_INSTRUCTIONS = os.getenv(
    "OPENAI_TTS_INSTRUCTIONS",
    "Speak naturally in clear Urdu with a calm, helpful male hospital appointment assistant tone. Use masculine Urdu grammar for the assistant.",
).strip()
OPENAI_TTS_CONNECT_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TTS_CONNECT_TIMEOUT_SECONDS", "30"))
OPENAI_TTS_READ_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TTS_READ_TIMEOUT_SECONDS", "300"))
