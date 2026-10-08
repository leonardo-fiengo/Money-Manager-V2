"""Verify dashboard installation leaves the financial ledger unchanged."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from money_manager.db.connection import dict_factory
from scripts.people_preview import projection

path=ROOT/'artifacts'/'premium-overview-ledger-before.json'
with sqlite3.connect(ROOT/'data'/'money_manager.sqlite3') as db:
    db.row_factory=dict_factory
    if sys.argv[1]=='before':
        columns,hashes=projection(db)
        # The app captures a dated net-worth snapshot on every normal startup.
        columns.pop('net_worth_snapshots',None);hashes.pop('net_worth_snapshots',None)
        path.write_text(json.dumps(dict(columns=columns,hashes=hashes)),encoding='utf-8')
        print(f'Captured {len(columns)} financial and preference tables.')
    else:
        before=json.loads(path.read_text(encoding='utf-8'))
        _,after=projection(db,before['columns'])
        changed=[table for table in after if after[table]!=before['hashes'][table]]
        report=dict(tables_checked=len(after),unchanged=not changed,changed_tables=changed,
                    integrity=db.execute('PRAGMA integrity_check').fetchone(),foreign_keys=db.execute('PRAGMA foreign_key_check').fetchall())
        (ROOT/'artifacts'/'premium-overview-ledger-audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report))
        if changed or report['foreign_keys']: raise ValueError('Existing ledger changed during installation.')
