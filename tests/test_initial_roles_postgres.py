"""The migrated database must supply roles without the E2E seed script."""
import importlib.util
import os
from pathlib import Path
import unittest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text

ACTIVE = {"ADMIN", "MAIN_KOORD", "KOORD", "VYK", "KER"}


@unittest.skipUnless(os.getenv('ORDER_TEST_DATABASE_URL'), 'Disposable PostgreSQL URL not supplied')
class InitialRoleTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ['ORDER_TEST_DATABASE_URL'])
        self.addCleanup(self.engine.dispose)

    def test_upgrade_supplies_all_active_roles_without_fixtures(self):
        with self.engine.connect() as conn:
            roles = set(conn.scalars(text('SELECT id FROM roles')))
            self.assertTrue(ACTIVE <= roles, f'Missing roles after migrations: {ACTIVE - roles}')

    def test_role_seed_is_repeatable_and_preserves_existing_names(self):
        path=Path('/app/alembic/versions/d2511200abcd_seed_active_roles.py')
        if not path.exists():
            path=Path(__file__).resolve().parents[1] / 'alembic/versions/d2511200abcd_seed_active_roles.py'
        spec=importlib.util.spec_from_file_location('seed_roles_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        with self.engine.connect() as conn:
            tx=conn.begin()
            try:
                conn.execute(text("UPDATE roles SET name='Synthetic existing name' WHERE id='KOORD'"))
                conn.execute(text("DELETE FROM roles WHERE id='VYK'"))
                with Operations.context(MigrationContext.configure(conn)):
                    migration.upgrade()
                    migration.upgrade()
                rows=dict(conn.execute(text('SELECT id, name FROM roles')).all())
                self.assertTrue(ACTIVE <= rows.keys())
                self.assertEqual(rows['KOORD'],'Synthetic existing name')
            finally:
                tx.rollback()

    def test_admin_can_create_workflow_users_through_real_api(self):
        from fastapi.testclient import TestClient
        from sqlalchemy.orm import Session
        from app.main import app
        from app.database.db_connection import get_db
        from app.models.user import User
        from app.core.security import hash_password, create_access_token
        with self.engine.connect() as conn:
            tx=conn.begin()
            db=Session(bind=conn,join_transaction_mode='create_savepoint')
            previous=dict(app.dependency_overrides)
            try:
                admin=User(login='synthetic_roles_admin',role_id='ADMIN',
                    password_hash=hash_password('synthetic-roles-test-only'))
                db.add(admin);db.flush()
                app.dependency_overrides[get_db]=lambda: db
                client=TestClient(app)
                headers={'Authorization':'Bearer '+create_access_token(admin.id)}
                department=client.post('/api/departments',headers=headers,json={
                    'id':'SYNROLE','name':'Synthetic role test','department_type':'апарат'})
                self.assertEqual(department.status_code,201,department.text)
                for role in ('MAIN_KOORD','KOORD','VYK','KER'):
                    response=client.post('/api/users/',headers=headers,json={
                        'login':'synthetic_'+role.lower(),'password':'synthetic-roles-test-only',
                        'role_id':role,'department_id':'SYNROLE'})
                    self.assertEqual(response.status_code,201,response.text)
                    self.assertEqual(response.json()['role_id'],role)
            finally:
                app.dependency_overrides.clear();app.dependency_overrides.update(previous)
                db.close();tx.rollback()
