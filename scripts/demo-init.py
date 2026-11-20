"""Generate local-only demo settings without overwriting an existing file."""
import secrets
from pathlib import Path
password=secrets.token_hex(24)
with Path('.env.demo').open('x') as f:
    f.write(f'POSTGRES_DB=bordergroup_demo\nPOSTGRES_USER=demo_user\nPOSTGRES_PASSWORD={password}\nDATABASE_URL=postgresql+psycopg://demo_user:{password}@db:5432/bordergroup_demo\nJWT_SECRET_KEY={secrets.token_hex(32)}\nDEMO_PASSWORD={secrets.token_urlsafe(18)}\nAPP_NAME=BorderGroup Demo\nDEBUG=false\nSQL_ECHO=false\n')
Path('.env.demo').chmod(0o600)
print('Created private .env.demo. Demo login: demo_admin; password is DEMO_PASSWORD in that file.')
