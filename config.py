import sys
from pathlib import Path


RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else RESOURCE_DIR
DATA_DIR = APP_DIR / "data"
DATABASE = DATA_DIR / "money_manager.sqlite3"
MERCHANT_LOGO_DIR = (
    DATA_DIR / "uploads" / "merchants"
    if getattr(sys, "frozen", False)
    else RESOURCE_DIR / "static" / "uploads" / "merchants"
)
SECRET_KEY = None  # Generated once per installation and persisted in DATA_DIR.
TEMPLATES_AUTO_RELOAD = not getattr(sys, "frozen", False)
