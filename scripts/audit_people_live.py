"""Compare the live database's original columns before and after an app restart."""
import json
import sqlite3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.people_preview import projection
from money_manager.db.connection import dict_factory

path=ROOT/'artifacts'/'people-live-before.json'
with sqlite3.connect(ROOT/'data'/'money_manager.sqlite3') as db:
    db.row_factory=dict_factory
    if sys.argv[1]=='before':
        columns,hashes=projection(db)
        path.write_text(json.dumps(dict(columns=columns,hashes=hashes),indent=2),encoding='utf-8')
        print(f'Captured {len(columns)} original tables before upgrade.')
    else:
        before=json.loads(path.read_text(encoding='utf-8'))
        _,after=projection(db,before['columns'])
        changed=[table for table in after if after[table]!=before['hashes'][table]]
        report=dict(existing_tables=len(after),unchanged=not changed,changed=changed,
                    integrity=db.execute('PRAGMA integrity_check').fetchone(),foreign_keys=db.execute('PRAGMA foreign_key_check').fetchall(),
                    counts={r['name']:db.execute('SELECT COUNT(*) AS n FROM '+r['name']).fetchone()['n'] for r in db.execute("SELECT name FROM sqlite_master WHERE name IN ('contacts','taxes','tax_payments','tax_estimates')")})
        (ROOT/'artifacts'/'people-live-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
        if changed or report['foreign_keys']: raise ValueError('Unexpected changes to existing data.')
