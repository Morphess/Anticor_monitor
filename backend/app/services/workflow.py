"""Внесення інформації про виконання, погодження координатором, підтвердні матеріали, перенесення строків.

Правила (хто що може, які переходи дозволені) — у rules.py; тут їх застосування до бази.
Кожна дія — одна транзакція; етап погодження змінюється умовним UPDATE ... WHERE review_state = :очікуваний,
тому дві одночасні дії над одним записом не можуть обидві пройти. Кожна зміна поля записується в журнал
зі старим і новим значенням.
"""
import hashlib
import uuid
from datetime import date
from pathlib import Path

from fastapi import Request, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from ..config import ALLOWED_EXT, MAX_FILE_MB, UPLOAD_DIR
from ..db import session
from ..models import DeadlineChange, Evidence, Execution, Measure, Risk, RiskMeasurement
from ..utils import fmt_num, now_utc
from . import journal, rules
from .rules import WorkflowError


def _fail(exc_or_message) -> None:
    session().rollback()
    raise exc_or_message if isinstance(exc_or_message, Exception) else WorkflowError(exc_or_message)


def _done() -> None:
    s = session()
    s.commit()
    s.expire_all()


def _measure_for(user: dict, measure_id: str, own_only: bool) -> Measure:
    m = session().get(Measure, measure_id)
    if not m or (own_only and m.executor_id != user["id"]):
        _fail("Захід не знайдено або він закріплений за іншим виконавцем")
    return m


def _execution(measure_id: str, period: str) -> Execution:
    """Запис про виконання за півріччя; створюється при першому зверненні (унікальність — у базі)."""
    s = session()
    ex = s.scalars(select(Execution).where(Execution.measure_id == measure_id, Execution.period == period)).first()
    if ex:
        return ex
    try:
        with s.begin_nested():
            ex = Execution(measure_id=measure_id, period=period)
            s.add(ex)
            s.flush()
    except IntegrityError:
        ex = s.scalars(select(Execution).where(Execution.measure_id == measure_id, Execution.period == period)).one()
    return ex


def _show(field: str, value) -> str:
    if value is None:
        return ""
    if field == "status":
        return rules.STATUS_LABELS.get(value, value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return fmt_num(value)
    return str(value)


# ---------- Виконавець ----------
def save_execution(user: dict, measure_id: str, period: str, *, status: str, actual_date: date | None,
                   result_text: str, indicator_fact: float | None, submit: bool, request: Request | None = None) -> None:
    """Зберігає внесену інформацію; submit=True — одразу подає на погодження (один крок для виконавця)."""
    s = session()
    _measure_for(user, measure_id, own_only=True)
    ex = _execution(measure_id, period)
    try:
        state_after_save = rules.next_review_state(ex.review_state, "save", user["role"])
        if status not in rules.STATUS_LABELS:
            raise WorkflowError("Оберіть стан виконання")
        if submit:
            rules.check_submission(status, result_text, actual_date, date.today())
            new_state = rules.next_review_state(state_after_save, "submit", user["role"])
        else:
            new_state = state_after_save
    except WorkflowError as e:
        _fail(e)

    new = {"status": status, "actual_date": actual_date, "result_text": (result_text or "").strip(),
           "indicator_fact": indicator_fact}
    changes = [(f, getattr(ex, f), v) for f, v in new.items() if getattr(ex, f) != v]
    now = now_utc()
    res = s.execute(
        update(Execution).where(Execution.id == ex.id, Execution.review_state == ex.review_state)
        .values(**new, review_state=new_state, entered_by_id=user["id"], entered_at=now)
        .execution_options(synchronize_session=False))
    if res.rowcount == 0:
        _fail("Запис щойно змінив інший користувач. Оновіть сторінку.")
    for field, old, value in changes:
        journal.log(user["id"], "внесено інформацію про виконання", "vykonannia", measure_id, field,
                    _show(field, old), _show(field, value), request, at=now)
    if submit:
        journal.log(user["id"], "подано на погодження", "vykonannia", measure_id, "review_state",
                    rules.REVIEW_LABELS[ex.review_state], rules.REVIEW_LABELS[new_state], request, at=now)
    _done()


def add_evidence(user: dict, measure_id: str, *, type_: str, name: str, doc_date: date | None, link: str = "",
                 upload: UploadFile | None = None, request: Request | None = None) -> str:
    """Додає підтвердний матеріал. Після додавання він не змінюється й не видаляється;
    SHA-256 фіксує вміст файлу (або опис, якщо це посилання чи документ без файлу)."""
    s = session()
    _measure_for(user, measure_id, own_only=True)
    name, type_, link = (name or "").strip(), (type_ or "").strip(), (link or "").strip()
    if not type_ or not (name or link) or not doc_date:
        _fail("Вкажіть тип, назву (або посилання) і дату документа")
    if doc_date > date.today():
        _fail("Дата документа не може бути в майбутньому")

    stored = original = None
    size = None
    data = b""
    if upload is not None and upload.filename:
        original = Path(upload.filename).name
        ext = Path(original).suffix.lower()
        if ext not in ALLOWED_EXT:
            _fail(f"Файл «{original}»: недопустимий формат. Дозволено: {', '.join(sorted(ALLOWED_EXT))}")
        limit = MAX_FILE_MB * 1024 * 1024
        data = upload.file.read(limit + 1)
        if len(data) > limit:
            _fail(f"Файл «{original}» більший за {MAX_FILE_MB} МБ")
        if not data:
            _fail(f"Файл «{original}» порожній")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        stored = f"{uuid.uuid4().hex}{ext}"
        (UPLOAD_DIR / stored).write_bytes(data)
        size = len(data)

    # Номер наступного матеріалу; блокування таблиці не потрібне — у разі збігу спрацює первинний ключ
    last = s.scalar(select(func.max(Evidence.id)))
    number = int(last.split("-")[1]) + 1 if last else 1
    now = now_utc()
    for attempt in range(5):
        eid = f"E-{number + attempt:03d}"
        digest = hashlib.sha256(data if data else f"{eid}|{measure_id}|{name or link}|{doc_date}".encode()).hexdigest()
        try:
            with s.begin_nested():
                s.add(Evidence(id=eid, measure_id=measure_id, type=type_, name=name or link, doc_date=doc_date,
                               link=link, uploaded_at=now, uploaded_by_id=user["id"], sha256=digest,
                               stored_name=stored, original_name=original, size=size))
                s.flush()
            break
        except IntegrityError:
            continue
    else:
        _fail("Не вдалося зберегти підтвердний матеріал. Спробуйте ще раз.")
    journal.log(user["id"], "завантажено підтвердний матеріал", "pidtverdzhennia", eid, "sha256", "", digest,
                request, at=now)
    _done()
    return eid


# ---------- Координатор ----------
def decide(user: dict, measure_id: str, period: str, action: str, comment: str = "",
           request: Request | None = None) -> None:
    """Погодити (approve) або повернути на доопрацювання (return, лише з коментарем)."""
    s = session()
    comment = (comment or "").strip()
    try:
        new_state = rules.next_review_state("submitted", action, user["role"])
        if action == "return":
            rules.check_return(comment)
    except WorkflowError as e:
        _fail(e)
    now = now_utc()
    res = s.execute(
        update(Execution)
        .where(Execution.measure_id == measure_id, Execution.period == period, Execution.review_state == "submitted")
        .values(review_state=new_state, review_comment=comment, reviewed_by_id=user["id"], reviewed_at=now)
        .execution_options(synchronize_session=False))
    if res.rowcount == 0:
        _fail("Цю інформацію вже розглянуто або її ще не подано. Оновіть сторінку.")
    journal.log(user["id"], "погоджено координатором" if action == "approve" else "повернуто на доопрацювання",
                "vykonannia", measure_id, "review_state", rules.REVIEW_LABELS["submitted"],
                rules.REVIEW_LABELS[new_state] + (f": {comment}" if comment else ""), request, at=now)
    _done()


def postpone(user: dict, measure_id: str, new_date: date | None, reason: str, request: Request | None = None) -> None:
    """Внутрішнє рішення про перенесення строку. Строк у затвердженій програмі не змінюється."""
    s = session()
    if user["role"] != "KOORD":
        _fail("Переносити строк може лише координатор програми")
    m = _measure_for(user, measure_id, own_only=False)
    if m.deadline_type != "data" or not m.deadline_date:
        _fail("Переносити можна лише строк заходу з конкретною датою")
    if not new_date or not (reason or "").strip():
        _fail("Вкажіть новий строк і причину перенесення")
    old = m.deadline_changes[-1].new_date if m.deadline_changes else m.deadline_date
    if new_date <= old:
        _fail("Новий строк має бути пізнішим за чинний")
    s.add(DeadlineChange(measure_id=measure_id, decision_date=date.today(), old_date=old, new_date=new_date,
                         reason=reason.strip(), approved_by_id=user["id"]))
    journal.log(user["id"], "змінено внутрішній строк", "zakhid", measure_id, "strok_aktualnyi",
                old.isoformat(), new_date.isoformat(), request)
    _done()


def add_risk_measurement(user: dict, risk_id: str, on: date | None, value: float | None, source: str,
                         request: Request | None = None) -> None:
    """Нове вимірювання індикатора стану ризику (за ним оцінюється, чи зменшився ризик)."""
    s = session()
    if user["role"] != "KOORD":
        _fail("Вносити вимірювання індикатора ризику може лише координатор програми")
    risk = s.get(Risk, risk_id)
    if not risk:
        _fail("Ризик не знайдено")
    if not on or value is None:
        _fail("Вкажіть дату і значення індикатора")
    if on > date.today():
        _fail("Дата вимірювання не може бути в майбутньому")
    try:
        with s.begin_nested():
            s.add(RiskMeasurement(risk_id=risk_id, date=on, value=value, source=(source or "").strip(),
                                  entered_by_id=user["id"]))
            s.flush()
    except IntegrityError:
        _fail("Вимірювання на цю дату вже є. Існуючі вимірювання не змінюються.")
    journal.log(user["id"], "внесено вимірювання індикатора ризику", "ryzyk", risk_id, on.isoformat(), "",
                fmt_num(value), request)
    _done()
