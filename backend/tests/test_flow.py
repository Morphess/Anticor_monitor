"""Повний цикл через HTTP: виконавець вносить і подає → координатор повертає → виконавець виправляє →
координатор погоджує. Плюс права доступу, незмінність матеріалів, журнал."""
import hashlib

from sqlalchemy import func, select

from app.db import session_scope
from app.models import Evidence, Execution, JournalEntry
from app.services import monitor

KOORD, KER, ADMIN = "U-002", "U-003", "U-001"


def pick(review_state: str) -> dict:
    """Захід із набору на потрібному етапі погодження, який має виконавця."""
    with session_scope():
        return next(m for m in monitor.snapshot()["measures"]
                    if m["review_state"] == review_state and m["executor_id"])


def execution(measure_id: str) -> Execution:
    with session_scope() as s:
        return s.scalars(select(Execution).where(Execution.measure_id == measure_id)).one()


def form(**over):
    return {"status": "vykonano", "actual_date": "2026-06-20", "indicator_fact": "12",
            "result_text": "Проведено 12 перевірок, складено акт № 7 від 20.06.2026.", "action": "submit", **over}


def test_login_and_home_by_role(app_client):
    assert "U-002" in app_client().get("/login").text
    assert app_client(KOORD).get("/").url.path == "/review"
    assert app_client(KER).get("/").url.path == "/panel"
    assert app_client(ADMIN).get("/").url.path == "/admin"
    assert app_client().get("/panel").url.path == "/login"


def test_pages_open_for_roles(app_client):
    koord = app_client(KOORD)
    for url in ["/review", "/panel", "/measures", "/measures/Z-01", "/risks", "/risks/KR01", "/flags", "/report",
                "/report.csv", "/report.csv?internal=1", "/journal", "/rules", "/program",
                "/measures?flag=any&section=R2", "/flags?code=RF1"]:
        assert koord.get(url).status_code == 200, url
    assert app_client(ADMIN).get("/admin").status_code == 200
    assert koord.get("/admin").status_code == 403
    assert app_client(KER).get("/review").status_code == 403


def test_executor_sees_only_own_measures(app_client):
    m = pick("draft")
    with session_scope():
        foreign = next(x for x in monitor.snapshot()["measures"] if x["executor_id"] != m["executor_id"])
    vyk = app_client(m["executor_id"])
    assert vyk.get("/my").status_code == 200
    assert vyk.get(f"/measures/{m['id']}").status_code == 200
    assert vyk.get(f"/measures/{foreign['id']}").status_code == 404
    assert vyk.get(f"/api/v1/measures/{foreign['id']}").status_code == 404
    assert all(x["executor_id"] == m["executor_id"] for x in vyk.get("/api/v1/measures").json())
    for url in ["/panel", "/risks", "/flags", "/report", "/journal", "/api/v1/flags"]:
        assert vyk.get(url).status_code == 403, url
    # чужий захід не можна ні змінити, ні доповнити матеріалом
    vyk.post(f"/measures/{foreign['id']}/execution", data=form())
    assert execution(foreign["id"]).status == foreign["status"]


def test_full_cycle(app_client):
    m = pick("draft")
    vyk, koord = app_client(m["executor_id"]), app_client(KOORD)

    # подати без опису результату не можна
    r = vyk.post(f"/measures/{m['id']}/execution", data=form(result_text=" "))
    assert "Опишіть результат" in r.text
    assert execution(m["id"]).review_state == "draft"

    # чернетка, потім подання
    vyk.post(f"/measures/{m['id']}/execution", data=form(action="save", status="v_roboti"))
    assert execution(m["id"]).review_state == "draft" and execution(m["id"]).status == "v_roboti"
    assert "Подано на погодження" in vyk.post(f"/measures/{m['id']}/execution", data=form()).text
    assert execution(m["id"]).review_state == "submitted"

    # після подання виконавець змінити не може
    r = vyk.post(f"/measures/{m['id']}/execution", data=form(result_text="Інший текст 1"))
    assert "редагування недоступне" in r.text
    assert execution(m["id"]).result_text.startswith("Проведено 12")

    # виконавець не може погодити сам себе; керівник теж
    assert vyk.post(f"/measures/{m['id']}/decision", data={"action": "approve"}).status_code == 403
    assert app_client(KER).post(f"/measures/{m['id']}/decision", data={"action": "approve"}).status_code == 403

    # повернення без коментаря не проходить, з коментарем — проходить
    assert "Вкажіть, що саме" in koord.post(f"/measures/{m['id']}/decision", data={"action": "return"}).text
    koord.post(f"/measures/{m['id']}/decision", data={"action": "return", "comment": "Додайте акт"})
    ex = execution(m["id"])
    assert ex.review_state == "returned" and ex.review_comment == "Додайте акт"

    # доопрацювання і погодження
    vyk.post(f"/measures/{m['id']}/execution", data=form(result_text="Проведено 12 перевірок, акт № 7 додано."))
    koord.post(f"/measures/{m['id']}/decision", data={"action": "approve"})
    assert execution(m["id"]).review_state == "approved"
    # повторне рішення неможливе
    assert "вже розглянуто" in koord.post(f"/measures/{m['id']}/decision", data={"action": "return", "comment": "x"}).text

    with session_scope() as s:
        log = s.scalars(select(JournalEntry).where(JournalEntry.object == "vykonannia",
                                                  JournalEntry.object_id == m["id"]).order_by(JournalEntry.id)).all()
    actions = [j.action for j in log]
    for expected in ["подано на погодження", "повернуто на доопрацювання", "погоджено координатором"]:
        assert expected in actions
    change = next(j for j in log if j.field == "result_text" and "акт № 7 додано" in j.new_value)
    assert change.old_value.startswith("Проведено 12") and change.user_id == m["executor_id"]


def test_evidence_is_hashed_and_immutable(app_client):
    m = pick("draft")
    vyk = app_client(m["executor_id"])
    content = b"synthetic act for tests"
    r = vyk.post(f"/measures/{m['id']}/evidence", data={"type": "акт", "name": "Акт № 7", "doc_date": "2026-06-20"},
                 files={"file": ("akt.txt", content, "text/plain")})
    assert "Підтвердний матеріал додано" in r.text
    with session_scope() as s:
        e = s.scalars(select(Evidence).where(Evidence.measure_id == m["id"]).order_by(Evidence.id.desc())).first()
        assert e.sha256 == hashlib.sha256(content).hexdigest() and e.id == "E-042"
    assert vyk.get(f"/evidence/{e.id}/file").content == content
    # недопустимий формат і майбутня дата
    r = vyk.post(f"/measures/{m['id']}/evidence", data={"type": "акт", "name": "x", "doc_date": "2026-06-20"},
                 files={"file": ("run.exe", b"MZ", "application/octet-stream")})
    assert "недопустимий формат" in r.text
    r = vyk.post(f"/measures/{m['id']}/evidence", data={"type": "акт", "name": "x", "doc_date": "2999-01-01"})
    assert "не може бути в майбутньому" in r.text
    # маршрутів зміни чи видалення матеріалів і журналу не існує
    from app.main import app
    for route in app.routes:
        methods = getattr(route, "methods", set()) or set()
        assert not ({"PUT", "PATCH", "DELETE"} & methods), route.path


def test_postpone_keeps_program_deadline(app_client):
    with session_scope():
        m = next(x for x in monitor.snapshot()["measures"] if x["deadline_type"] == "data" and not x["postponements"])
    koord = app_client(KOORD)
    r = koord.post(f"/measures/{m['id']}/postpone", data={"new_date": "2027-12-31", "reason": "Затримка постачання"})
    assert "Внутрішній строк змінено" in r.text
    with session_scope():
        after = next(x for x in monitor.snapshot()["measures"] if x["id"] == m["id"])
    assert after["deadline_date"] == m["deadline_date"] and after["deadline_text"] == m["deadline_text"]
    assert after["internal_deadline"].isoformat() == "2027-12-31"
    assert after["portal_state"] == m["portal_state"]          # звіт рахується від строку за програмою
    r = koord.post(f"/measures/{m['id']}/postpone", data={"new_date": "2027-01-01", "reason": "ще"})
    assert "має бути пізнішим" in r.text


def test_risk_measurement_and_api(app_client):
    koord = app_client(KOORD)
    r = koord.post("/risks/KR01/measurement", data={"on": "2026-07-01", "value": "3,5", "source": "тест"})
    assert "Вимірювання внесено" in r.text
    assert "вже є" in koord.post("/risks/KR01/measurement", data={"on": "2026-07-01", "value": "9"}).text
    assert len(koord.get("/api/v1/flags").json()) == 29
    assert len(koord.get("/api/v1/report").json()["rows"]) == 50
    assert koord.get("/api/v1/risks").json()[0]["id"] == "KR01"
    assert koord.get("/api/v1/measures?period=bad").status_code == 400
    assert app_client().get("/api/v1/measures").status_code == 401
    assert koord.get("/health").json() == {"status": "ok"}


def test_admin_period_and_users(app_client):
    admin = app_client(ADMIN)
    assert "Період вказують так" in admin.post("/admin/period", data={"period": "2026"}).text
    admin.post("/admin/period", data={"period": "2026-H2", "as_of": "2026-12-01"})
    with session_scope():
        assert monitor.current_period() == "2026-H2" and monitor.as_of_date().isoformat() == "2026-12-01"
        snap = monitor.snapshot()
        assert all(not m["exists"] for m in snap["measures"])       # нове півріччя — нові записи про виконання
    assert admin.get("/panel").status_code == 200
    # вимкнений користувач не входить
    admin.post("/admin/users/U-003", data={"active": "0"})
    assert app_client().post("/login", data={"user_id": "U-003"}).url.path == "/login"
    assert "власний обліковий запис" in admin.post("/admin/users/U-001", data={"active": "0"}).text
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(JournalEntry).where(JournalEntry.object == "korystuvach",
                                                                             JournalEntry.field == "active")) == 1
