"""Start an isolated UI preview and audit the additive migration against a live copy."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from money_manager.db.connection import dict_factory
from money_manager.db.migration import run_migrations
from money_manager import create_app


def projection(db,tables=None):
    if tables is None:
        tables={r['name']:[c['name'] for c in db.execute(f'PRAGMA table_xinfo("{r["name"]}")')] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'transaction_search%' AND name!='schema_migrations'")}
    hashes={}
    for table,columns in tables.items():
        rows=db.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM "'+table+'" ORDER BY rowid').fetchall()
        hashes[table]=dict(count=len(rows),sha256=hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
    return tables,hashes


if __name__=='__main__':
    folder=ROOT/'data'/'people-preview';folder.mkdir(exist_ok=True)
    database=folder/'preview.sqlite3'
    if not database.exists():
        with sqlite3.connect(ROOT/'data'/'money_manager.sqlite3') as source,sqlite3.connect(database) as target: source.backup(target)
    with sqlite3.connect(database) as db:
        db.row_factory=dict_factory;db.execute('PRAGMA foreign_keys=ON')
        columns,before=projection(db)
        run_migrations(db)
        _,after=projection(db,columns)
        report=dict(existing_tables=len(before),unchanged=before==after,foreign_keys=db.execute('PRAGMA foreign_key_check').fetchall(),integrity=db.execute('PRAGMA integrity_check').fetchone(),before=before,after=after)
        (ROOT/'artifacts'/'people-migration-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        if not report['unchanged'] or report['foreign_keys']: raise ValueError('Migration changed existing data.')
    config=type('PreviewConfig',(),dict(DATA_DIR=folder,DATABASE=database,MERCHANT_LOGO_DIR=ROOT/'static'/'uploads'/'merchants',SECRET_KEY='isolated-people-preview',TESTING=False,TEMPLATES_AUTO_RELOAD=True))
    create_app(config).run(host='127.0.0.1',port=5001,debug=False,use_reloader=False)
