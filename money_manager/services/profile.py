from money_manager.db.connection import get_db
from money_manager.db.atomic import atomic


def local_profile():
    return get_db().execute('SELECT * FROM local_profile WHERE id=1').fetchone() or dict(id=1,display_name='',email='',phone='',avatar_data=None)


def save_profile(name, email=None, phone=None, avatar_data=None, remove_photo=False):
    name = (name or '').strip()
    if len(name)>60 or any(ord(c)<32 for c in name):
        raise ValueError('Use a display name of up to 60 characters.')
    db = get_db()
    old = local_profile()
    email = old['email'] if email is None else email.strip()
    phone = old['phone'] if phone is None else phone.strip()
    if len(email)>254 or (email and ('@' not in email or any(c.isspace() for c in email))):
        raise ValueError('Enter a valid email address.')
    if len(phone)>50: raise ValueError('Use a phone number of up to 50 characters.')
    photo = None if remove_photo else avatar_data or old['avatar_data']
    with atomic(db):
        db.execute("INSERT INTO local_profile(id,display_name,email,phone,avatar_data) VALUES(1,?,?,?,?) ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,email=excluded.email,phone=excluded.phone,avatar_data=excluded.avatar_data,updated_at=CURRENT_TIMESTAMP", (name,email,phone,photo))


def profile_photo(upload):
    import base64
    if not upload or not upload.filename: return None
    data = upload.read(2*1024*1024+1)
    if len(data)>2*1024*1024: raise ValueError('Choose a profile photo smaller than 2 MB.')
    if data.startswith(b'\x89PNG\r\n\x1a\n') and b'IEND' in data[-16:]: mime = 'image/png'
    elif data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9'): mime = 'image/jpeg'
    elif data[:4]==b'RIFF' and data[8:12]==b'WEBP': mime = 'image/webp'
    else: raise ValueError('Choose a PNG, JPEG, or WebP photo.')
    return 'data:' + mime + ';base64,' + base64.b64encode(data).decode('ascii')
