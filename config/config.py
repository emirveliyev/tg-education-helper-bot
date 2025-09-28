import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
API_BASE = os.getenv("API_BASE")
GEMINI_MODEL = os.getenv("GEMINI_MODEL")
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "5000"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.8"))
ADMIN = int(os.getenv("ADMIN", "7787510838"))

if not TELEGRAM_API_TOKEN:
    raise RuntimeError("TELEGRAM_API_TOKEN не указан")

DATA_DIR = "./data"
os.makedirs(DATA_DIR, exist_ok=True)