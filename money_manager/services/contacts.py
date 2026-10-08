from money_manager.db.connection import get_db
from money_manager.db.atomic import atomic


def list_contacts(active_only=True):
    return get_db().execute('SELECT * FROM contacts ' + ('WHERE is_active=1 ' if active_only else '') + 'ORDER BY name COLLATE NOCASE,id').fetchall()


def get_contact(contact_id):
    return get_db().execute('SELECT * FROM contacts WHERE id=?', (contact_id,)).fetchone()


def save_contact(data, contact_id=None):
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    phone = (data.get('phone') or '').strip()
    notes = (data.get('notes') or '').strip()
    if not name or len(name)>100 or any(ord(c)<32 for c in name):
        raise ValueError('Give this contact a name of up to 100 characters.')
    if len(email)>254 or (email and ('@' not in email or any(c.isspace() for c in email))):
        raise ValueError('Enter a valid email address.')
    if len(phone)>50 or len(notes)>2000:
        raise ValueError('Use a phone number up to 50 characters and notes up to 2,000 characters.')
    db = get_db()
    with atomic(db):
        if contact_id:
            if not get_contact(contact_id): raise ValueError('Contact not found.')
            db.execute('UPDATE contacts SET name=?,email=?,phone=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (name,email,phone,notes,contact_id))
        else:
            contact_id = db.execute('INSERT INTO contacts(name,email,phone,notes) VALUES(?,?,?,?)',(name,email,phone,notes)).lastrowid
    return contact_id


def set_contact_active(contact_id, active):
    with atomic(get_db()):
        get_db().execute('UPDATE contacts SET is_active=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(int(active),contact_id))
