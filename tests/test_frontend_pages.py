import os
import unittest
from datetime import date

# Налаштування для імпорту застосунку без локального .env (як у CI).
# Робочий engine створюється при імпорті, але не підключається: get_db підмінено на SQLite.
os.environ.setdefault("APP_NAME", "Anticor Monitor test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SQL_ECHO", "false")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/unused")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only-32b")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — реєструє всі таблиці
from app.core.security import hash_password
from app.database.base import Base
from app.database.db_connection import get_db
from app.main import app
from app.models import Department, Measure, Order, Program, Role, Section, User

PASSWORD = "demo-password-123"


def measure(mid, n, text, **extra):
    return Measure(
        id=mid, program_id="AKP-TEST", section_id="R1", sequence_number=n, description=text,
        deadline_description="до кінця року", deadline_type="ongoing",
        completion_indicator="Виконано", required_evidence="Протокол", resources="Не потребує", **extra,
    )


class MonitorPagesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine, expire_on_commit=False)

        with Session() as db:
            for code in ("ADMIN", "KOORD", "VYK"):
                db.add(Role(id=code, name=code))
            db.add(Section(id="R1", number=1, title="Розділ один"))
            db.add(Department(id="P01", name="Відділ кадрів", department_type="апарат"))
            db.add(Program(
                id="AKP-TEST", title="Тестова програма", organization_name="Вигадана установа",
                start_date=date(2026, 1, 1), end_date=date(2027, 12, 31),
                approval_reference="Наказ № 1", approval_status="затверджено", goals="Перевірка",
            ))
            db.flush()
            db.add(User(login="admin", password_hash=hash_password(PASSWORD), role_id="ADMIN"))
            db.add(User(login="vyk", password_hash=hash_password(PASSWORD), role_id="VYK",
                        program_id="AKP-TEST", department_id="P01"))
            db.flush()
            db.add(measure("Z-01", 1, "Провести навчання", responsible_department_id="P01"))
            db.add(measure("Z-02", 2, "Чужий захід"))
            db.flush()
            db.add(Order(id="O-1", number="15-к", title="Про навчання", measure_id="Z-01"))
            db.add(Order(id="O-2", number="99", title="Про інше", measure_id="Z-02"))
            db.commit()

        def override_db():
            db = Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def auth(self, login):
        res = self.client.post("/api/auth/token", data={"username": login, "password": PASSWORD})
        self.assertEqual(res.status_code, 200, res.text)
        return {"Authorization": "Bearer " + res.json()["access_token"]}

    def coordinator_item(self, headers, measure_id):
        data = self.client.get("/api/coordinator/programs", headers=headers).json()
        items = [i for p in data["programs"] for s in p["sections"] for i in s["items"]]
        return next(i for i in items if i["measure_id"] == measure_id)

    def test_pages_and_static(self):
        for path in ("/login", "/executor", "/coordinator"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            self.assertIn("api.js", res.text)
        for path in ("/static/css/monitor.css", "/static/js/api.js",
                     "/static/js/executor.js", "/static/js/coordinator.js", "/static/js/login.js"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_me_and_auth_required(self):
        me = self.client.get("/api/auth/me", headers=self.auth("vyk")).json()
        self.assertEqual((me["role_id"], me["department_id"]), ("VYK", "P01"))
        self.assertNotIn("password_hash", me)
        self.assertEqual(self.client.get("/api/executor/rows").status_code, 401)
        self.assertEqual(self.client.get("/api/coordinator/programs").status_code, 401)

    def test_executor_sees_only_own_department(self):
        data = self.client.get("/api/executor/rows", headers=self.auth("vyk")).json()
        self.assertEqual(data["unit"], "Відділ кадрів")
        self.assertEqual([r["id"] for r in data["rows"]], ["Z-01"])
        self.assertEqual(data["rows"][0]["order_title"], "Про навчання")
        self.assertEqual(data["rows"][0]["st"], "not")

    def test_order_check_then_coordinator_approves(self):
        vyk, admin = self.auth("vyk"), self.auth("admin")
        check = lambda num: self.client.post(
            "/api/executor/check-order", json={"measure_id": "Z-01", "number": num}, headers=vyk).json()

        self.assertFalse(check("")["ok"])
        self.assertIn("немає в реєстрі", check("404")["message"])
        self.assertIn("іншого заходу", check("99")["message"])
        res = check("№ 15-к")
        self.assertTrue(res["ok"])
        self.assertEqual(res["st"], "review")

        item = self.coordinator_item(admin, "Z-01")
        self.assertEqual(item["units"][0]["st"], "review")
        self.assertEqual(item["units"][0]["order"], "15-к")
        self.assertEqual(item["units"][0]["organ"], "Відділ кадрів")

        res = self.client.post("/api/coordinator/status", json={"measure_id": "Z-01", "status": "done"}, headers=admin)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self.coordinator_item(admin, "Z-01")["units"][0]["st"], "done")
        row = self.client.get("/api/executor/rows", headers=vyk).json()["rows"][0]
        self.assertEqual((row["st"], row["entered"]), ("done", "15-к"))

    def test_executor_cannot_change_status_or_foreign_measure(self):
        vyk = self.auth("vyk")
        res = self.client.post("/api/coordinator/status", json={"measure_id": "Z-01", "status": "done"}, headers=vyk)
        self.assertEqual(res.status_code, 403)
        res = self.client.post("/api/executor/check-order", json={"measure_id": "Z-02", "number": "99"}, headers=vyk)
        self.assertFalse(res.json()["ok"])
        self.assertFalse(self.client.get("/api/coordinator/programs", headers=vyk).json()["can_edit"])

    def test_admin_page_departments_and_create_user(self):
        self.assertIn("admin.js", self.client.get("/admin").text)
        self.assertEqual(self.client.get("/static/js/admin.js").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/departments", headers=self.auth("vyk")).status_code, 403)

        admin = self.auth("admin")
        deps = self.client.get("/api/admin/departments", headers=admin).json()
        self.assertEqual(deps, [{"id": "P01", "name": "Відділ кадрів"}])

        new = {"login": "new.user", "password": "long-password-123", "role_id": "VYK",
               "department_id": "P01", "position": "Інспектор", "program_id": "AKP-TEST"}
        res = self.client.post("/api/users/", json=new, headers=admin)
        self.assertEqual(res.status_code, 201, res.text)
        logins = {u["login"] for u in self.client.get("/api/users/?limit=100", headers=admin).json()}
        self.assertIn("new.user", logins)
        res =self.client.post("/api/auth/token", data={"username": "new.user", "password": "long-password-123"})
        self.assertEqual(res.status_code, 200)

    def test_unknown_status_rejected(self):
        res = self.client.post("/api/coordinator/status", json={"measure_id": "Z-01", "status": "bad"},
                               headers=self.auth("admin"))
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
