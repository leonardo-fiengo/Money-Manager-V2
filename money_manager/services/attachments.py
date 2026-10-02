from pathlib import Path
from uuid import uuid4

from flask import current_app
from werkzeug.utils import secure_filename

from money_manager.db.connection import get_db

ALLOWED={'.pdf','.png','.jpg','.jpeg','.webp','.txt'}


def attachment_directory():
    path=current_app.config['DATA_DIR']/'attachments'
    path.mkdir(exist_ok=True)
    return path


def save_attachment(transaction_id,file):
    filename=secure_filename(file.filename or '')
    extension=Path(filename).suffix.lower()
    if not filename or extension not in ALLOWED: raise ValueError('Attach a PDF, image, or text file.')
    content=file.read(5*1024*1024+1)
    if not content or len(content)>5*1024*1024: raise ValueError('Attachments must be nonempty and under 5 MB.')
    db=get_db()
    if not db.execute('SELECT 1 FROM transactions WHERE id=?',(transaction_id,)).fetchone(): raise ValueError('Transaction not found.')
    name=uuid4().hex+extension; target=attachment_directory()/name
    target.write_bytes(content)
    try:
        with db: db.execute('INSERT INTO transaction_attachments(transaction_id,filename,storage_name) VALUES(?,?,?)',(transaction_id,filename,name))
    except Exception:
        target.unlink(missing_ok=True); raise


def attachments_for(transaction_id):
    return get_db().execute('SELECT * FROM transaction_attachments WHERE transaction_id=? ORDER BY id',(transaction_id,)).fetchall()
