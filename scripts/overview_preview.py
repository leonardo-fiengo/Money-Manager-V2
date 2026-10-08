"""Run the overview against an isolated copy of the local ledger."""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from money_manager import create_app

if __name__ == '__main__':
    folder = ROOT / 'data' / 'overview-preview'
    folder.mkdir(exist_ok=True)
    database = folder / 'preview.sqlite3'
    if not database.exists():
        with sqlite3.connect(ROOT / 'data' / 'money_manager.sqlite3') as source, sqlite3.connect(database) as target:
            source.backup(target)
    config = type('PreviewConfig', (), dict(DATA_DIR=folder, DATABASE=database,
        MERCHANT_LOGO_DIR=ROOT / 'static' / 'uploads' / 'merchants',
        SECRET_KEY='isolated-overview-preview', TESTING=False, TEMPLATES_AUTO_RELOAD=True))
    create_app(config).run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)
