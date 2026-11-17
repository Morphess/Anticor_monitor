import os
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal

# Налаштування як у test_frontend_pages: без .env, БД — SQLite у пам'яті.
os.environ.setdefault("APP_NAME", "Anticor Monitor test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SQL_ECHO", "false")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:1/unused")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests-only-32b")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — реєструє всі таблиці
from app.core.security import hash_password
from app.database.base import Base
from app.database.db_connection import get_db
from app.main import app
from app.models import (
    ActionLog, DeadlineChange, Department, Execution, Measure, Program, Risk, RiskMeasurement, Role, Section, User,
)
from app.services.manager_service import compute_signals
from app.services.monitor_service import current_period

PASSWORD = "demo-password-123"


def risk(rid, level, score, **extra):
    p, i = {4: (2, 2), 9: (3, 3), 16: (4, 4), 1: (1, 1)}[score]
    return Risk(
        id=rid, process_name="Закупівлі", title=f"Ризик {rid}", description="Опис", risk_sources="Джерело",
        existing_controls="Контроль", probability_score=p, impact_score=i, score=score, level=level,
        owner_department_id="P02", indicator_name="Частка порушень", indicator_unit="%",
        indicator_direction="decrease", indicator_baseline_value=Decimal(100), indicator_target_value=Decimal(50),
        target_date=date(2026, 12, 31), **extra,
    )


def measure(mid, n, dep, **extra):
    values = dict(deadline_description="постійно", deadline_type="ongoing")
    values.update(extra)
    return Measure(
        id=mid, program_id="AKP-TEST", section_id="R1", sequence_number=n, description=f"Захід {mid}",
        responsible_department_id=dep, completion_indicator="Виконано", required_evidence="Протокол",
        resources="Не потребує", **values,
    )


class ManagerCabinetTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                                    poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        period = current_period()

        with self.Session() as db:
            for code in ("ADMIN", "KOORD", "VYK", "KER", "ANAL"):
                db.add(Role(id=code, name=code))
            db.add(Section(id="R1", number=1, title="Розділ один"))
            db.add(Department(id="P01", name="Відділ кадрів", department_type="апарат"))
            db.add(Department(id="P02", name="Відділ закупівель", department_type="апарат"))
            db.add(Program(id="AKP-TEST", title="Тестова програма", organization_name="Вигадана установа",
                           start_date=date(2026, 1, 1), end_date=date(2027, 12, 31),
                           approval_reference="Наказ № 1", approval_status="затверджено", goals="Перевірка"))
            db.flush()
            for login, role in (("ker", "KER"), ("anal", "ANAL"), ("admin", "ADMIN"), ("vyk", "VYK")):
                db.add(User(login=login, password_hash=hash_password(PASSWORD), role_id=role, department_id="P01"))
            db.add(risk("KR01", "high", 9))       # пов'язаний із Z-03, індикатор майже не змінився
            db.add(risk("KR02", "critical", 16))  # без заходів -> RF7d
            db.add(risk("KR03", "low", 1))        # низький без заходів -> сигналу немає
            db.flush()
            db.add(RiskMeasurement(risk_id="KR01", measured_on=date(2026, 6, 30), value=Decimal(98), source="звіт"))
            # RF1 ×2 у P01 -> ще й RF6b для підрозділу
            db.add(measure("Z-01", 1, "P01", deadline_type="date", deadline_on=date(2020, 1, 1),
                           deadline_description="до 01.01.2020"))
            db.add(measure("Z-02", 2, "P01", deadline_type="date", deadline_on=date(2020, 2, 1),
                           deadline_description="до 01.02.2020"))
            # Виконано без підтвердження (RF2), показник нижче цілі (RF5), ризик не зменшився (RF3)
            db.add(measure("Z-03", 3, "P02", risk_id="KR01", indicator_target=Decimal(10), indicator_unit="шт."))
            # Строк переносили двічі (RF6a)
            db.add(measure("Z-04", 4, "P02"))
            db.flush()
            db.add(Execution(measure_id="Z-03", period=period, status="completed", status_label="Виконано",
                             approved_by_coordinator=True, indicator_actual=Decimal(5), result_description=""))
            for k in range(2):
                db.add(DeadlineChange(measure_id="Z-04", decision_date=date(2026, 3 + k, 1),
                                      previous_deadline=date(2026, 4 + k, 1), new_deadline=date(2026, 5 + k, 1),
                                      reason="Брак ресурсів"))
            db.commit()

        def override_db():
            db = self.Session()
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

    def overview(self, login="ker"):
        res = self.client.get("/api/manager/overview", headers=self.auth(login))
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def test_pages_render(self):
        for path, script in (("/manager", "manager.js"), ("/analyst", "analyst.js")):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, path)
            self.assertIn(script, res.text)
            self.assertIn("reports.js", res.text)
            self.assertIn('id="tab-reports"', res.text)
            self.assertIn('id="tab-programs"', res.text)
        # Панелей аналітики в керівника немає
        self.assertNotIn('id="tab-analytics"', self.client.get("/manager").text)
        self.assertIn('id="tab-analytics"', self.client.get("/analyst").text)
        for js in ("manager", "reports", "charts", "tabs"):
            self.assertEqual(self.client.get(f"/static/js/{js}.js").status_code, 200, js)

    def test_signals_follow_rules(self):
        with self.Session() as db:
            signals = compute_signals(db)
        keys = sorted(s["key"] for s in signals)
        self.assertEqual(keys, sorted([
            "RF1:Z-01", "RF1:Z-02", "RF6b:P01", "RF2:Z-03", "RF5:Z-03", "RF3:Z-03", "RF6a:Z-04", "RF7d:KR02",
        ]))
        by_key = {s["key"]: s for s in signals}
        self.assertEqual(by_key["RF1:Z-01"]["suggested_department_id"], "P01")
        self.assertEqual(by_key["RF1:Z-01"]["program"], "Тестова програма")
        self.assertIsNone(by_key["RF7d:KR02"]["program"])
        self.assertEqual(by_key["RF3:Z-03"]["suggested_department_id"], "P02")  # власник ризику
        self.assertTrue(any("4%" in fact for fact in by_key["RF3:Z-03"]["why"]))
        self.assertTrue(all(s["rule"] and s["why"] and s["recommendation"] for s in signals))
        # Спершу — висока увага
        severities = [s["severity"] for s in signals]
        self.assertEqual(severities, sorted(severities, key=lambda v: v != "high"))

    def test_signal_context(self):
        with self.Session() as db:
            by_key = {s["key"]: s for s in compute_signals(db)}
        facts = dict(by_key["RF1:Z-01"]["context"]["facts"])
        self.assertEqual(facts["Розділ"], "1. Розділ один")
        self.assertEqual(facts["Програма"], "Тестова програма")
        row = by_key["RF1:Z-01"]["context"]["table"]["rows"][0]
        self.assertEqual((row["cells"][0], row["st"]), ("Відділ кадрів", "not"))
        self.assertEqual(len(by_key["RF6b:P01"]["context"]["table"]["rows"]), 2)
        self.assertIn("Існуючі заходи контролю", dict(by_key["RF7d:KR02"]["context"]["facts"]))

    def test_analytics_requests_and_reports(self):
        ker, anal = self.auth("ker"), self.auth("anal")
        future = (date.today() + timedelta(days=7)).isoformat()
        post = lambda url, body, h: self.client.post("/api/analytics" + url, json=body, headers=h)

        # Запит керівника
        self.assertEqual(post("/requests", {"topic": " ", "due_on": future}, ker).status_code, 400)
        self.assertEqual(post("/requests", {"topic": "Т", "due_on": "2020-01-01"}, ker).status_code, 400)
        self.assertEqual(post("/requests", {"topic": "Т", "due_on": future}, anal).status_code, 403)
        res = post("/requests", {"topic": "Чому відстає Відділ кадрів", "question": "Причини прострочень",
                                 "program_id": "AKP-TEST", "due_on": future}, ker)
        self.assertEqual(res.status_code, 200, res.text)
        rid = res.json()["id"]

        # Аналітик бачить запит і бере в роботу
        inbox = self.client.get("/api/analytics/inbox", headers=anal).json()
        self.assertEqual([(r["id"], r["status"]) for r in inbox["requests"]], [(rid, "new")])
        self.assertTrue(inbox["can_report"])
        self.assertEqual(post(f"/requests/{rid}/take", None, ker).status_code, 403)
        self.assertEqual(post(f"/requests/{rid}/take", None, anal).json()["status"], "in_progress")
        self.assertEqual(post(f"/requests/{rid}/take", None, anal).status_code, 409)

        # Звіт
        report = {"request_id": rid, "program_id": "AKP-TEST", "title": "Відставання Відділу кадрів",
                  "findings": "", "proposals": "Провести нараду"}
        self.assertEqual(post("/reports", report, anal).status_code, 400)
        self.assertEqual(post("/reports", dict(report, findings="x"), ker).status_code, 403)
        res = post("/reports", dict(report, findings="Два заходи прострочено"), anal)
        self.assertEqual(res.status_code, 200, res.text)
        rep = res.json()
        snap = rep["snapshot"]
        self.assertEqual((snap["counts"]["total"], snap["counts"]["overdue"], snap["scope"]), (4, 2, "Тестова програма"))
        self.assertEqual({d["name"] for d in snap["departments"]}, {"Відділ кадрів", "Відділ закупівель"})
        self.assertEqual(post("/reports", dict(report, findings="ще"), anal).status_code, 409)

        # Керівник отримує звіт як новий; після відкриття — прочитаний
        inbox = self.client.get("/api/analytics/inbox", headers=ker).json()
        self.assertEqual(inbox["requests"][0]["status"], "answered")
        self.assertEqual(inbox["requests"][0]["report_id"], rep["id"])
        self.assertTrue(inbox["reports"][0]["unread"])
        full = self.client.get(f"/api/analytics/reports/{rep['id']}", headers=ker).json()
        self.assertEqual(full["findings"], "Два заходи прострочено")
        self.assertEqual(full["request_question"], "Причини прострочень")
        self.assertFalse(self.client.get("/api/analytics/inbox", headers=ker).json()["reports"][0]["unread"])

        # Звіт з власної ініціативи й заборони
        res = post("/reports", {"title": "Огляд", "findings": "Загальний стан"}, anal)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["snapshot"]["scope"], "Усі програми")
        for login in ("vyk", "admin"):
            self.assertEqual(self.client.get("/api/analytics/inbox", headers=self.auth(login)).status_code, 403)
        self.assertEqual(self.client.get("/api/analytics/reports/999", headers=ker).status_code, 404)

    def test_access(self):
        self.assertEqual(self.client.get("/api/manager/overview").status_code, 401)
        for login in ("vyk", "anal"):
            self.assertEqual(self.client.get("/api/manager/overview", headers=self.auth(login)).status_code, 403)
        self.assertTrue(self.overview("ker")["can_decide"])
        self.assertFalse(self.overview("admin")["can_decide"])
        ker = self.auth("ker")
        # Аналітику керівник отримує звітами від аналітика, а не напряму
        self.assertEqual(self.client.get("/api/analyst/overview", headers=ker).status_code, 403)
        self.assertFalse(self.client.get("/api/coordinator/programs", headers=ker).json()["can_edit"])
        body = {"signal_key": "RF1:Z-01", "decision": "dismiss", "comment": "Причина"}
        for login in ("admin", "anal", "vyk"):
            res = self.client.post("/api/manager/decisions", json=body, headers=self.auth(login))
            self.assertEqual(res.status_code, 403, login)

    def test_decisions(self):
        ker = self.auth("ker")
        post = lambda **body: self.client.post("/api/manager/decisions", json=body, headers=ker)
        future = (date.today() + timedelta(days=10)).isoformat()

        self.assertEqual(post(signal_key="RF1:Z-01", decision="assign", due_on=future).status_code, 400)
        res = post(signal_key="RF1:Z-01", decision="assign", department_id="P01", due_on="2020-01-01")
        self.assertIn("минулому", res.json()["detail"])
        self.assertEqual(post(signal_key="RF1:Z-01", decision="dismiss", comment="  ").status_code, 400)
        self.assertEqual(post(signal_key="RF9:Z-99", decision="dismiss", comment="x").status_code, 404)

        res = post(signal_key="RF1:Z-01", decision="assign", department_id="P01", due_on=future,
                   comment="Доповісти на нараді")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual((res.json()["decision"], res.json()["department"]), ("assign", "Відділ кадрів"))
        self.assertIn("Тестова програма", res.json()["object"])
        self.assertEqual(post(signal_key="RF1:Z-01", decision="dismiss", comment="ще раз").status_code, 409)

        res = post(signal_key="RF7d:KR02", decision="dismiss", comment="Захід готується окремим наказом")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIsNone(res.json()["department"])

        data = self.overview()
        pending = {s["key"] for s in data["signals"]}
        self.assertNotIn("RF1:Z-01", pending)
        self.assertNotIn("RF7d:KR02", pending)
        self.assertIn("RF1:Z-02", pending)
        self.assertEqual([d["signal_key"] for d in data["decisions"]][::-1], ["RF1:Z-01", "RF7d:KR02"])

        with self.Session() as db:
            logs = db.scalars(select(ActionLog).where(ActionLog.entity_type == "management_decision")).all()
        self.assertEqual(len(logs), 2)
        self.assertTrue(any("Відділ кадрів" in log.new_value for log in logs))


if __name__ == "__main__":
    unittest.main()
