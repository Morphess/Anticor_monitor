"""Create an initial account only in the explicitly named local demo database."""
import os
from sqlalchemy import select, func
from sqlalchemy.engine import make_url
from app.database.db_connection import SessionLocal
from app.core.config import settings
from app.core.security import hash_password
from app.models.user import User
from app.models.role import Role

url=make_url(settings.DATABASE_URL)
if url.host != 'db' or url.database != 'bordergroup_demo' or url.username != 'demo_user':
    raise SystemExit('Refusing to bootstrap a non-demo database')
password=os.environ['DEMO_PASSWORD']
if len(password)<12:
    raise SystemExit('Demo password must contain at least 12 characters')
with SessionLocal.begin() as db:
    if db.scalar(select(func.count()).select_from(User)):
        raise SystemExit('Existing users preserved; demo bootstrap skipped')
    if not db.get(Role,'ADMIN'):
        db.add(Role(id='ADMIN',name='Адміністратор демонстрації'))
        db.flush()
    db.add(User(login='demo_admin',password_hash=hash_password(password),role_id='ADMIN'))
print('Demo administrator created')
