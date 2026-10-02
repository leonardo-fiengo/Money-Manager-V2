"""Password-derived authenticated encryption; no passwords in exports or logs."""
import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from flask import current_app

MAGIC=b'MMBACKUP3'


def _derive(password,salt):
    return base64.urlsafe_b64encode(Argon2id(salt=salt,length=32,iterations=3,lanes=4,memory_cost=65536).derive(password.encode('utf-8')))


def _wrapper():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(current_app.secret_key.encode()).digest()))


def encryption_config():
    path=current_app.config['DATA_DIR']/'.backup-encryption.json'
    if not path.exists(): return None
    config=json.loads(path.read_text(encoding='utf-8'))
    try: config['key']=_wrapper().decrypt(config['wrapped'].encode())
    except (InvalidToken,KeyError): raise ValueError('The saved backup key cannot be opened. Set the backup password again.') from None
    return config


def configure_encryption(password):
    if len(password or '')<12 or len(password)>500:
        raise ValueError('Choose a backup password of 12 to 500 characters.')
    salt=os.urandom(16); key=_derive(password,salt)
    config=dict(salt=base64.b64encode(salt).decode(),wrapped=_wrapper().encrypt(key).decode())
    path=current_app.config['DATA_DIR']/'.backup-encryption.json'
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(config),encoding='utf-8'); temporary.replace(path)


def encrypt_snapshot(content):
    config=encryption_config()
    if not config: return content
    return MAGIC+base64.b64decode(config['salt'])+Fernet(config['key']).encrypt(content)


def decrypt_snapshot(content,password=None):
    if not content.startswith(MAGIC): return content
    salt=content[len(MAGIC):len(MAGIC)+16]; token=content[len(MAGIC)+16:]
    if password:
        key=_derive(password,salt)
    else:
        config=encryption_config()
        if not config or base64.b64decode(config['salt'])!=salt:
            raise ValueError('Enter the password used to encrypt this backup.')
        key=config['key']
    try: return Fernet(key).decrypt(token)
    except InvalidToken: raise ValueError('The password is incorrect or this encrypted backup is damaged.') from None
