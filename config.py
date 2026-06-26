from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE = DATA_DIR / "money_manager.sqlite3"
MERCHANT_LOGO_DIR = BASE_DIR / "static" / "uploads" / "merchants"
SECRET_KEY = "local-dev-secret-key"
