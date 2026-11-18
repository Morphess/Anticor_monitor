import os
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models
from app.models.role import Role
from app.models.user import User

from app.schemas.departments import DepartmentCreate, DepartmentUpdate
from app.services.department_services import DepartmentService


@unittest.skipUnless(
    os.environ.get("DEPARTMENT_TEST_DATABASE_URL"),
    "Не задано URL окремої тестової PostgreSQL",
)
class DepartmentsPostgresTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(os.environ["DEPARTMENT_TEST_DATABASE_URL"])
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(
            bind=self.connection,
            join_transaction_mode="create_savepoint",
        )
        self.service = DepartmentService(self.db)

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.connection.close()
        self.engine.dispose()

    def test_crud_and_duplicate(self):
        created = self.service.create(
            DepartmentCreate(
                id="TEST01",
                name="Тестовий підрозділ",
                department_type="Тест",
            )
        )
        self.assertEqual(created.id, "TEST01")
        self.assertEqual(
            self.service.get_by_id("TEST01").name,
            "Тестовий підрозділ",
        )
        self.assertTrue(
            any(item.id == "TEST01" for item in self.service.get_all())
        )

        updated = self.service.update(
            "TEST01",
            DepartmentUpdate(name="Оновлена назва"),
        )
        self.assertEqual(updated.name, "Оновлена назва")

        with self.assertRaises(HTTPException) as duplicate:
            self.service.create(
                DepartmentCreate(
                    id="TEST01",
                    name="Дублікат",
                    department_type="Тест",
                )
            )
        self.assertEqual(duplicate.exception.status_code, 409)

        self.service.delete("TEST01")

        with self.assertRaises(HTTPException) as missing:
            self.service.get_by_id("TEST01")
        self.assertEqual(missing.exception.status_code, 404)
    def test_delete_department_keeps_user_without_department(self):
        self.db.add(Role(id="TEST_ROLE", name="Тестова роль"))
        self.service.create(
            DepartmentCreate(
                id="TEST02",
                name="Тестовий підрозділ",
                department_type="Тест",
            )
        )

        user = User(
            login="department_test_user",
            password_hash="synthetic-test-hash",
            role_id="TEST_ROLE",
            department_id="TEST02",
        )
        self.db.add(user)
        self.db.flush()
        user_id = user.id

        self.service.delete("TEST02")

        self

    def test_delete_department_keeps_user_without_department(self):
        role = self.db.get(Role, "ADMIN")
        if role is None:
            self.db.add(Role(id="ADMIN", name="Адміністратор"))
            self.db.flush()

        self.service.create(
            DepartmentCreate(
                id="TEST02",
                name="Тестовий підрозділ",
                department_type="Тест",
            )
        )
        user = User(
            login="department_delete_test",
            password_hash="synthetic-test-hash",
            role_id="ADMIN",
            department_id="TEST02",
        )
        self.db.add(user)
        self.db.flush()
        user_id = user.id

        self.service.delete("TEST02")

        self.db.expire_all()
        saved_user = self.db.get(User, user_id)
        self.assertIsNotNone(saved_user)
        self.assertIsNone(saved_user.department_id)