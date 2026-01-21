import os

APP_TITLE = "Vision Drink Survey"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(BASE_DIR, "best.pt"))

INPUT_DIR  = os.getenv("INPUT_DIR",  os.path.join(BASE_DIR, "uploads"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(BASE_DIR, "outputs", "sautrain"))

STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(BASE_DIR, "vision_drink_survey.db")

POLL_SECONDS = float(os.getenv("POLL_SECONDS", "0.5"))
STABLE_SECONDS = float(os.getenv("STABLE_SECONDS", "0.6"))

EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

LAST_RAW = os.path.join(STATIC_DIR, "last.jpg")

# --- CẤU HÌNH GEMINI AI ---
# Key của bạn (đã lấy từ ảnh bạn gửi)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "***********************") 

# Sửa thành bản 1.5-flash (bản ổn định nhất hiện nay)
GEMINI_MODEL = "gemini-2.5-flash" 
USE_GEMINI = True
