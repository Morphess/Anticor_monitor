"""Create synthetic fixtures once in the disposable E2E database. Never reset data."""
import hashlib
import io
import os
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.engine import make_url
from reportlab.pdfgen import canvas

url = make_url(os.environ['DATABASE_URL'])
if (os.environ.get('BORDERGROUP_E2E') != '1' or url.host != 'db'
        or url.database != 'bordergroup_e2e' or url.username != 'e2e_user' or url.query):
    raise SystemExit('Refusing to seed anything except the isolated E2E database')

import app.models
from app.database.db_connection import SessionLocal
from app.core.security import hash_password
from app.models.role import Role
from app.models.department import Department
from app.models.user import User
from app.models.program import Program
from app.models.section import Section
from app.models.measure import Measure
from app.models.program_workflow import ProgramDepartment, MeasureAssignment
from app.models.order import Order
from app.models.order_version import OrderVersion
from app.services.order_document_storage import OrderDocumentStorage

PASSWORD = 'synthetic-playwright-only-2026'
year = date.today().year
storage = OrderDocumentStorage()
stream = io.BytesIO()
pdf = canvas.Canvas(stream)
pdf.drawString(60, 780, 'SYNTHETIC TEST ORDER PW-ORDER-1')
pdf.drawString(60, 750, 'Conduct one integrity training and prepare a report.')
pdf.save()
content = stream.getvalue()
key = 'playwright-synthetic-order.pdf'
path = storage._path(key)
path.write_bytes(content)
path.chmod(0o600)
with SessionLocal.begin() as db:
    if db.scalar(select(func.count()).select_from(User)):
        raise SystemExit('E2E database already contains users; recreate only the disposable stack')
    for code in ['ADMIN', 'MAIN_KOORD', 'KOORD', 'VYK']:
        if db.get(Role, code) is None:
            db.add(Role(id=code, name='Synthetic ' + code))
    db.add(Department(id='PW-HQ', name='Synthetic HQ', department_type='апарат', notes='E2E'))
    db.flush()
    for code in ['PW-TEAM', 'PW-OTHER']:
        db.add(Department(id=code, name='Synthetic ' + code, parent_id='PW-HQ', department_type='апарат', notes='E2E'))
    db.flush()
    users = {}
    for login, role, dep in [('pw_admin','ADMIN',None),('pw_main','MAIN_KOORD','PW-HQ'),
                             ('pw_coord','KOORD','PW-TEAM'),('pw_executor','VYK','PW-TEAM'),
                             ('pw_outside','VYK','PW-OTHER'),('pw_unrelated_coord','KOORD','PW-OTHER')]:
        row=User(login=login, role_id=role, department_id=dep, password_hash=hash_password(PASSWORD))
        db.add(row); users[login]=row
    db.flush()
    db.add(Program(id='PW-PROGRAM', title='Playwright synthetic program', organization_name='Synthetic institution',
                   start_date=date(year,1,1), end_date=date(year,12,31), approval_reference='PW-ORDER-1',
                   approval_status='approved', goals='Synthetic workflow', notes='E2E', has_restricted_information=False,
                   coordinator_department_id='PW-HQ', created_by_user_id=users['pw_main'].id))
    if db.get(Section,'R3') is None:
        db.add(Section(id='R3', number=3, title='Synthetic training'))
    db.flush()
    db.add(Measure(id='PW000001',program_id='PW-PROGRAM',section_id='R3',sequence_number=1,
                   description='Conduct one synthetic integrity training', responsible_department_id='PW-TEAM',
                   deadline_type='date',deadline_on=date(year,12,31),deadline_description='Year end',
                   completion_indicator='One training',indicator_target=1,indicator_unit='training',
                   required_evidence='Registered order',resources='Synthetic'))
    db.add(ProgramDepartment(program_id='PW-PROGRAM',department_id='PW-TEAM',sent_by_user_id=users['pw_main'].id))
    db.flush()
    db.add(MeasureAssignment(measure_id='PW000001',user_id=users['pw_executor'].id,
                            department_id='PW-TEAM',assigned_by_user_id=users['pw_coord'].id))
    db.add(Order(id='PW-ORDER-1',number='PW-ORDER-1',title='Synthetic order',issued_on=date.today()))
    db.flush()
    db.add(OrderVersion(order_id='PW-ORDER-1',version=1,sha256=hashlib.sha256(content).hexdigest(),
                        storage_key=key,original_filename='synthetic-order.pdf',content_type='application/pdf',
                        size_bytes=len(content),change_reason='Synthetic Playwright fixture'))
print('Synthetic E2E fixtures ready')
