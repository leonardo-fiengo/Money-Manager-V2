"""Benchmark the read-only overview with a disposable, synthetic ledger."""
import hashlib
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from money_manager import create_app
from money_manager.db.connection import get_db, close_db
from money_manager.services.accounts import create_account
from money_manager.services.budgets import upsert_budget


def seed():
    db=get_db()
    accounts=[create_account(f'Test account {i+1:02d}', 'investment' if i==19 else 'bank',1000+i*100) for i in range(20)]
    categories=db.execute("SELECT id,name FROM categories WHERE type='expense' LIMIT 4").fetchall()
    today=date.today()
    rows=[]
    for i in range(6000):
        day=(today-timedelta(days=i%720)).isoformat()
        kind='income' if i%7==0 else 'investment' if i%23==0 else 'expense'
        amount=10000+(i%41)*100 if kind=='income' else 100+(i%37)*20
        rows.append((day,kind,amount,amount,categories[i%len(categories)]['name'] if kind=='expense' else None,
                     f'Test ledger entry {i}',accounts[i%len(accounts)]))
    db.executemany('INSERT INTO transactions(date,type,amount_minor,amount_eur_minor,category,description,account_id) VALUES(?,?,?,?,?,?,?)',rows)
    for i in range(5):
        db.execute("INSERT INTO transactions(date,type,amount_minor,amount_eur_minor,description,account_id,status) VALUES(?,'expense',?,?,?,?,'pending')",
            ((today+timedelta(days=i+1)).isoformat(),1000+i*100,1000+i*100,f'Test scheduled payment {i+1}',accounts[i]))
    db.commit()
    for category in categories:
        upsert_budget(dict(month=today.strftime('%Y-%m'),category_id=category['id'],amount=500))


def fingerprint():
    return hashlib.sha256(json.dumps(get_db().execute('SELECT * FROM transactions ORDER BY id').fetchall(),sort_keys=True).encode()).hexdigest()


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='overview-benchmark-',dir=ROOT/'data') as folder:
        root=Path(folder)
        app=create_app(type('BenchmarkConfig',(),dict(DATA_DIR=root,DATABASE=root/'test.sqlite3',
            MERCHANT_LOGO_DIR=root/'logos',SECRET_KEY='benchmark',TESTING=True,TEMPLATES_AUTO_RELOAD=True)))
        with app.app_context():
            seed()
            before=fingerprint()
            client=app.test_client()
            queries=[]
            get_db().set_trace_callback(lambda sql:queries.append(None))
            if '--profile' in sys.argv:
                import cProfile
                profiler=cProfile.Profile()
                profiler.enable()
            started=perf_counter(); response=client.get('/'); elapsed=perf_counter()-started
            if '--profile' in sys.argv:
                profiler.disable()
                import pstats
                pstats.Stats(profiler).sort_stats('cumtime').print_stats(22)
            count=len(queries);get_db().set_trace_callback(None)
            assert response.status_code==200
            assert fingerprint()==before
            started=perf_counter(); history=client.get('/overview/balance?range=all'); history_time=perf_counter()-started
            assert history.status_code==200
            assert history.json['points'][-1]['balance']==history.json['total']
            report=dict(transactions=6005,accounts=24,dashboard_seconds=round(elapsed,3),dashboard_queries=count,
                        history_seconds=round(history_time,3),financial_records_unchanged=True)
            (ROOT/'artifacts'/'premium-overview-performance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report,indent=2),flush=True)
        if '--serve' in sys.argv:
            app.run(host='127.0.0.1',port=5002,debug=False,use_reloader=False)
