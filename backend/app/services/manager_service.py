"""Кабінет керівника: рекомендації за явними правилами й рішення за ними.

Правила взято зі словника набору організаторів (сигнали RF*). Кожен сигнал показує
користувачу правило, факти, що до нього привели, і рекомендацію. Сигнал — привід
перевірити, а не висновок про порушення; рішення ухвалює керівник.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ActionLog, Department, ManagementDecision, Measure, Risk, User,
)
from app.services.monitor_service import (
    STATUSES, _department_name, _execution, _fmt, _measure_query, _status_key, current_period,
)

DECIDER_ROLES = ("KER",)
VIEW_ROLES = ("KER", "ADMIN")

RISK_LEVELS = {"low": "низький", "medium": "середній", "high": "високий", "critical": "критичний"}

# Пояснення правил людською мовою — показуються на сторінці.
RULES = {
    "RF1": "Строк заходу — конкретна дата, вона вже минула, а захід не погоджено як виконаний.",
    "RF2": "Захід позначено виконаним або поданим на розгляд, але до нього немає жодного підтвердження "
           "(наказу чи іншого документа).",
    "RF3": "Захід, пов'язаний із корупційним ризиком, виконано, а індикатор ризику пройшов менше 10 % шляху "
           "від базового до цільового значення. Можливе формальне закриття.",
    "RF5": "Захід виконано або подано, але фактичне значення показника менше за цільове.",
    "RF6a": "Строк заходу переносили два або більше разів.",
    "RF6b": "У підрозділі два або більше прострочених заходи.",
    "RF7d": "Ризик високого або критичного рівня, а в програмі немає жодного заходу щодо нього.",
}


class ManagerError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _num(value: Decimal | None) -> str:
    return f"{value.normalize():f}" if value is not None else "—"


def _days(n: int) -> str:
    a, b = n % 10, n % 100
    word = "день" if a == 1 and b != 11 else ("дні" if 2 <= a <= 4 and not 12 <= b <= 14 else "днів")
    return f"{n} {word}"


def _measure_label(m: Measure) -> str:
    return f"Захід {m.section.number}.{m.sequence_number}: {m.description}"


def _signal(code, obj_key, severity, title, object_label, why, recommendation, department_id, due_days, today,
            program_id=None):
    return {
        "key": f"{code}:{obj_key}",
        "code": code,
        "severity": severity,
        "title": title,
        "object": object_label,
        "program_id": program_id,
        "why": why,
        "rule": RULES[code],
        "recommendation": recommendation,
        "suggested_department_id": department_id,
        "suggested_due": (today + timedelta(days=due_days)).isoformat(),
    }


def _risk_progress(risk: Risk) -> tuple[float, Decimal, date] | None:
    """Частка шляху від базового до цільового значення за останнім вимірюванням."""
    if not risk.measurements or risk.indicator_target_value == risk.indicator_baseline_value:
        return None
    last = max(risk.measurements, key=lambda r: r.measured_on)
    span = risk.indicator_target_value - risk.indicator_baseline_value
    return float((last.value - risk.indicator_baseline_value) / span), last.value, last.measured_on


def compute_signals(db: Session, today: date | None = None) -> list[dict]:
    today = today or date.today()
    period = current_period(today)
    measures = db.scalars(
        _measure_query()
        .options(
            selectinload(Measure.evidences),
            selectinload(Measure.deadline_changes),
            selectinload(Measure.risk).selectinload(Risk.measurements),
        )
        .order_by(Measure.program_id, Measure.section_id, Measure.sequence_number)
    ).all()

    signals: list[dict] = []
    overdue_by_dep: dict[str, list[Measure]] = {}

    for m in measures:
        execution = _execution(m, period)
        st = _status_key(execution)
        dep_id = m.responsible_department_id
        dep_name = m.responsible_department.name if m.responsible_department else "не призначено"
        label = _measure_label(m)
        status_fact = f"Статус: {STATUSES[st].lower()}"

        # RF1 — прострочено
        if m.deadline_on and m.deadline_on < today and st != "done":
            late = (today - m.deadline_on).days
            signals.append(_signal(
                "RF1", m.id, "high", "Строк виконання минув", label,
                [f"Строк: {_fmt(m.deadline_on)} — минуло {_days(late)}", status_fact,
                 f"Відповідальний підрозділ: {dep_name}"],
                f"Доручити підрозділу «{dep_name}» завершити захід і подати підтвердження.",
                dep_id, 14, today, m.program_id))
            if dep_id:
                overdue_by_dep.setdefault(dep_id, []).append(m)

        # RF2 — виконано без підтвердження
        if st in ("done", "review") and not m.evidences and not m.orders:
            signals.append(_signal(
                "RF2", m.id, "medium", "Виконання не підтверджено документами", label,
                [status_fact, "Підтвердних матеріалів: 0"],
                f"Доручити підрозділу «{dep_name}» додати підтвердні матеріали: наказ, протокол або акт.",
                dep_id, 7, today, m.program_id))

        # RF3 — формальне закриття
        if m.risk and st == "done":
            progress = _risk_progress(m.risk)
            if progress and progress[0] < 0.10:
                share, value, measured = progress
                r = m.risk
                signals.append(_signal(
                    "RF3", m.id, "high", "Захід виконано, а ризик не зменшився", label,
                    [f"Ризик {r.id}: {r.title}",
                     f"Індикатор «{r.indicator_name}»: базове {_num(r.indicator_baseline_value)}, "
                     f"ціль {_num(r.indicator_target_value)} {r.indicator_unit}",
                     f"Останнє вимірювання {_fmt(measured)}: {_num(value)} — пройдено {max(share, 0) * 100:.0f}% шляху"],
                    "Доручити власнику ризику з'ясувати, чому захід не вплинув на ризик, і запропонувати додатковий захід.",
                    r.owner_department_id or dep_id, 30, today, m.program_id))

        # RF5 — показник нижче цілі
        if (st in ("done", "review") and execution is not None and m.indicator_target is not None
                and execution.indicator_actual is not None and execution.indicator_actual < m.indicator_target):
            unit = f" {m.indicator_unit}" if m.indicator_unit else ""
            signals.append(_signal(
                "RF5", m.id, "medium", "Показник не досягнув цілі", label,
                [f"Ціль: {_num(m.indicator_target)}{unit}", f"Факт: {_num(execution.indicator_actual)}{unit}",
                 status_fact],
                f"Доручити підрозділу «{dep_name}» пояснити відставання й подати план досягнення цілі.",
                dep_id, 14, today, m.program_id))

        # RF6a — повторні перенесення строку
        if len(m.deadline_changes) >= 2:
            moves = sorted(m.deadline_changes, key=lambda c: c.decision_date)
            signals.append(_signal(
                "RF6a", m.id, "medium", "Строк переносили кілька разів", label,
                [f"Перенесень: {len(moves)}"] + [
                    f"{_fmt(c.previous_deadline)} → {_fmt(c.new_deadline)}: {c.reason}" for c in moves],
                f"Доручити підрозділу «{dep_name}» пояснити причини перенесень; розглянути зміну відповідального.",
                dep_id, 14, today, m.program_id))

    # RF6b — підрозділ із кількома простроченими заходами
    for dep_id, items in overdue_by_dep.items():
        if len(items) < 2:
            continue
        name = items[0].responsible_department.name
        signals.append(_signal(
            "RF6b", dep_id, "high", "У підрозділі кілька прострочених заходів", f"Підрозділ: {name}",
            [f"Прострочених заходів: {len(items)}"] + [
                f"{i.section.number}.{i.sequence_number} {i.description} — строк {_fmt(i.deadline_on)}" for i in items],
            f"Провести нараду з керівником підрозділу «{name}» і затвердити план усунення прострочень.",
            dep_id, 7, today))

    # RF7d — високий ризик без заходів
    risks = db.scalars(select(Risk).options(selectinload(Risk.measures)).where(Risk.level.in_(("high", "critical")))).all()
    for r in risks:
        if r.measures:
            continue
        signals.append(_signal(
            "RF7d", r.id, "high", "Серйозний ризик без жодного заходу", f"Ризик {r.id}: {r.title}",
            [f"Рівень ризику: {RISK_LEVELS.get(r.level, r.level)} (бал {r.score})", "Заходів у програмі: 0"],
            "Доручити власнику ризику підготувати захід для включення до програми.",
            r.owner_department_id, 30, today))

    order = {"high": 0, "medium": 1}
    signals.sort(key=lambda s: order[s["severity"]])
    return signals


def _decision_dict(d: ManagementDecision) -> dict:
    return {
        "signal_key": d.signal_key,
        "rule_code": d.rule_code,
        "title": d.signal_title,
        "object": d.object_label,
        "decision": d.decision,
        "department": d.responsible_department.name if d.responsible_department else None,
        "due": _fmt(d.due_on) if d.due_on else None,
        "comment": d.comment,
        "by": d.decided_by.position or d.decided_by.login,
        "at": d.decided_at.strftime("%d.%m.%Y %H:%M"),
    }


def manager_page(db: Session, user: User, today: date | None = None) -> dict:
    today = today or date.today()
    period = current_period(today)
    decisions = db.scalars(
        select(ManagementDecision)
        .options(selectinload(ManagementDecision.responsible_department), selectinload(ManagementDecision.decided_by))
        .where(ManagementDecision.period == period)
        .order_by(ManagementDecision.decided_at.desc())
    ).all()
    decided = {d.signal_key for d in decisions}
    signals = [s for s in compute_signals(db, today) if s["key"] not in decided]
    departments = db.scalars(select(Department).order_by(Department.name)).all()
    return {
        "unit": _department_name(db, user.department_id) or user.position or user.login,
        "period": period,
        "today": _fmt(today),
        "can_decide": user.role_id in DECIDER_ROLES,
        "departments": [{"id": d.id, "name": d.name} for d in departments],
        "signals": signals,
        "decisions": [_decision_dict(d) for d in decisions],
    }


def decide(db: Session, user: User, signal_key: str, decision: str, department_id: str | None,
           due_on: date | None, comment: str, today: date | None = None) -> dict:
    today = today or date.today()
    period = current_period(today)
    comment = (comment or "").strip()

    if decision not in ("assign", "dismiss"):
        raise ManagerError("Невідоме рішення")
    signal = next((s for s in compute_signals(db, today) if s["key"] == signal_key), None)
    if signal is None:
        raise ManagerError("Рекомендацію не знайдено: можливо, дані вже змінилися. Оновіть сторінку.", 404)
    if db.scalar(select(ManagementDecision.id).where(
            ManagementDecision.signal_key == signal_key, ManagementDecision.period == period)):
        raise ManagerError("Рішення за цією рекомендацією вже ухвалено", 409)

    if decision == "assign":
        if not department_id or db.get(Department, department_id) is None:
            raise ManagerError("Оберіть відповідальний підрозділ")
        if due_on is None:
            raise ManagerError("Вкажіть строк виконання доручення")
        if due_on < today:
            raise ManagerError("Строк доручення не може бути в минулому")
    else:
        if not comment:
            raise ManagerError("Вкажіть причину, чому рекомендацію відхилено")
        department_id, due_on = None, None

    record = ManagementDecision(
        signal_key=signal_key, period=period, rule_code=signal["code"], signal_title=signal["title"],
        object_label=signal["object"], decision=decision, responsible_department_id=department_id,
        due_on=due_on, comment=comment, decided_by_user_id=user.id, decided_at=datetime.now(),
    )
    db.add(record)
    db.flush()

    summary = (f"Доручено: {_department_name(db, department_id)}, до {_fmt(due_on)}" if decision == "assign"
               else "Відхилено")
    if comment:
        summary += f". {comment}"
    db.add(ActionLog(
        id=str(uuid.uuid4()), occurred_at=record.decided_at, actor_user_id=user.id,
        action=f"Рішення керівника за сигналом {signal['code']}", entity_type="management_decision",
        entity_id=str(record.id), field_name="decision", old_value=None, new_value=summary,
    ))
    db.commit()
    db.refresh(record)
    return _decision_dict(record)
