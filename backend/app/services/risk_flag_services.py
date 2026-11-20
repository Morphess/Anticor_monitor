"""Risk Flags RF1–RF7e із dictionary.md та додатковий RF8 (невдалий наказ).

На вхід надходять ORM-об'єкти SQLAlchemy або об'єкти з тими самими полями.
Детектор нічого не змінює у БД. Усі правила відтворювані й пояснювані.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import re
from typing import Any, Iterable

from app.schemas.risk_flags import RiskFlagRead

_COMPLETED = {"completed", "vykonano"}
_PARTIAL = {"partial", "chastkovo"}
_FINISHED = _COMPLETED | _PARTIAL
_HIGH_RISK = {"high", "critical", "високий", "критичний"}
_WORDS = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
_URL = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)


def _effective_state(execution):
    """Legacy RF rules evaluate reported completion, not approval workflow codes."""
    if execution is None:
        return None
    status = execution.status
    if status == "approved" and not getattr(execution, "document_changed", False):
        return getattr(execution, "outcome_status", None) or "completed"
    if status == "rejected":
        return "not_completed"
    if status == "pending":
        return "in_progress"
    return status  # old pre-migration instances, if used by legacy tests

_MESSAGES = {
    "RF1": "Прострочений захід: строк за програмою минув, захід не виконано",
    "RF2": "Немає підтвердних матеріалів для виконаного або частково виконаного заходу",
    "RF3": "Формальне закриття: захід виконано, а показник ризику майже не змінився",
    "RF4": "Опис результату повторює зміст заходу без цифр чи посилань",
    "RF5": "Фактичний показник виконання нижче цільового",
    "RF6": "Повторні перенесення строку або кілька прострочених заходів у підрозділі",
    "RF7a": "Фактична дата виконання поза звітним періодом",
    "RF7b": "Усі підтвердні документи датовані пізніше за дату виконання",
    "RF7c": "Захід не виконано, а пояснення причин відсутнє",
    "RF7d": "Ризик високого/критичного рівня без заходів",
    "RF7e": "Заповнений опис для заходу, строк якого не настав",
    "RF8": "Спроба підтвердити захід наказом, якого немає в реєстрі",
}


def period_bounds(period: str) -> tuple[date, date]:
    """Підтримуваний формат звітного періоду: YYYY-H1 / YYYY-H2."""
    match = re.fullmatch(r"(\d{4})-H([12])", period)
    if not match:
        raise ValueError("Період має формат YYYY-H1 або YYYY-H2")
    year, half = int(match.group(1)), int(match.group(2))
    if half == 1:
        return date(year, 1, 1), date(year, 6, 30)
    return date(year, 7, 1), date(year, 12, 31)


def _word_stems(value: str) -> set[str]:
    return {word[:5] for word in _WORDS.findall(value.lower())}


def jaccard_similarity(first: str, second: str) -> float:
    a = _word_stems(first)
    b = _word_stems(second)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_not_due(measure: Any, execution: Any, end: date) -> bool:
    return (
        measure.deadline_type == "date"
        and measure.deadline_on is not None
        and measure.deadline_on > end
        and (execution is None or _effective_state(execution) not in _FINISHED)
    )


def _is_overdue(measure: Any, execution: Any, end: date) -> bool:
    return (
        measure.deadline_type == "date"
        and measure.deadline_on is not None
        and measure.deadline_on <= end
        and (execution is None or _effective_state(execution) not in _COMPLETED)
    )


def _report_not_completed(measure: Any, execution: Any, end: date) -> bool:
    return (
        not _is_not_due(measure, execution, end)
        and (execution is None or _effective_state(execution) not in _FINISHED)
    )


def _risk_progress(risk: Any, actual: Any) -> Decimal | None:
    if actual is None:
        return None
    baseline = Decimal(str(risk.indicator_baseline_value))
    target = Decimal(str(risk.indicator_target_value))
    denominator = target - baseline
    if denominator == 0:
        return None  # відсутній коректний напрям/діапазон покращення
    return (Decimal(str(actual)) - baseline) / denominator


def detect_rf8_flags(
    *, period: str, as_of: date,
    measures: Iterable[Any],
    invalid_order_attempts: Iterable[Any] = (),
) -> list[RiskFlagRead]:
    """RF8 можна читати всередині поточного періоду (не чекаючи кінця H1/H2)."""
    period_start, period_end = period_bounds(period)
    if as_of < period_start:
        raise ValueError("Дата зрізу не може бути раніше початку звітного періоду")

    allowed_ids = {measure.id for measure in measures}
    rejected = defaultdict(list)
    for attempt in invalid_order_attempts:
        day = attempt.attempted_at.date()
        if attempt.measure_id in allowed_ids and period_start <= day <= min(as_of, period_end):
            rejected[attempt.measure_id].append(attempt)

    result = []
    for measure_id, attempts in sorted(rejected.items()):
        distinct_numbers = ", ".join(sorted({str(a.order_number) for a in attempts}))
        # Ім'я/ПІБ не вигадуємо: у users є login, а журнал зберігає ID.
        # Видалений користувач усе одно ідентифікується через історичний ID.
        actors = sorted({
            (str(getattr(a, "actor_login", None) or "Користувач")
             + " (ID " + str(a.actor_user_id) + ")")
            for a in attempts
        })
        result.append(RiskFlagRead(
            code="RF8", object_type="zakhid", object_id=str(measure_id),
            period=period, message=_MESSAGES["RF8"],
            explanation=(f"невдалі спроби: {len(attempts)}; номери: {distinct_numbers}; "
                         f"Хто виконав дію: {', '.join(actors)}"),
        ))
    return result


def detect_risk_flags(
    *,
    period: str,
    as_of: date,
    measures: Iterable[Any],
    executions: Iterable[Any],
    confirmed_orders: Iterable[Any],
    deadline_changes: Iterable[Any],
    risks: Iterable[Any],
    measurements: Iterable[Any],
    invalid_order_attempts: Iterable[Any] = (),
) -> list[RiskFlagRead]:
    """Обчислити всі сигнали на конкретний період та дату зрізу.

    За відсутності значень, потрібних для правила, воно не дає припущень.
    """
    period_start, period_end = period_bounds(period)
    if as_of < period_end:
        raise ValueError("Дата зрізу не може бути раніше завершення звітного періоду")

    measures = list(measures)
    risks = list(risks)
    executions_by_id = {
        row.measure_id: row for row in executions if row.period == period
    }
    orders_by_measure = defaultdict(list)
    for order in confirmed_orders:
        if order.submitted_at is None or order.submitted_at.date() <= as_of:
            orders_by_measure[order.measure_id].append(order)

    deadline_by_measure = Counter()
    for change in deadline_changes:
        if change.decision_date <= as_of:
            deadline_by_measure[change.measure_id] += 1

    risk_by_id = {risk.id: risk for risk in risks}
    measure_risk_ids = {m.risk_id for m in measures if m.risk_id}

    # На кінець звітного періоду беремо останнє вимірювання в межах цього півріччя.
    latest_measurements: dict[str, Any] = {}
    for row in measurements:
        if period_start <= row.measured_on <= period_end:
            old = latest_measurements.get(row.risk_id)
            if old is None or row.measured_on > old.measured_on:
                latest_measurements[row.risk_id] = row

    signals: list[RiskFlagRead] = []
    overdue_by_department = defaultdict(list)

    def add(code: str, object_type: str, object_id: str, explanation: str):
        signals.append(RiskFlagRead(
            code=code,
            object_type=object_type,
            object_id=str(object_id),
            period=period,
            message=_MESSAGES[code],
            explanation=explanation,
        ))

    for measure in measures:
        execution = executions_by_id.get(measure.id)
        state = _effective_state(execution)
        finished = state in _FINISHED
        description = (execution.result_description or "").strip() if execution else ""
        proof_orders = orders_by_measure.get(measure.id, [])
        not_due = _is_not_due(measure, execution, period_end)

        # RF1 — використовуємо первинний строк програми, а не перенесений.
        if _is_overdue(measure, execution, period_end):
            add("RF1", "zakhid", measure.id, f"строк {measure.deadline_on}, статус {state or 'відсутній'}")
            if measure.responsible_department_id:
                overdue_by_department[measure.responsible_department_id].append(measure.id)

        # RF2 — виконання без наданих підтвердних матеріалів.
        if finished and not proof_orders:
            add("RF2", "zakhid", measure.id, "підтвердних матеріалів: 0")

        # RF3 — другий розділ, захід виконано, а індикатор ризику майже стоїть.
        if measure.section_id == "R2" and state in _COMPLETED and measure.risk_id:
            risk = risk_by_id.get(measure.risk_id)
            latest = latest_measurements.get(measure.risk_id)
            if risk is not None and latest is not None:
                progress = _risk_progress(risk, latest.value)
                if progress is not None and progress < Decimal("0.10"):
                    add(
                        "RF3", "zakhid", measure.id,
                        f"ризик {risk.id}: {risk.indicator_baseline_value} → {latest.value}; "
                        f"ціль {risk.indicator_target_value}; пройдено {progress:.1%} шляху",
                    )

        # RF4 — Жаккар на перших 5 літерах слів, без цифр і URL в описі.
        if finished and description and not re.search(r"\d", description) and not _URL.search(description):
            similarity = jaccard_similarity(description, measure.description)
            if similarity >= 0.6:
                add("RF4", "zakhid", measure.id, f"схожість опису {similarity:.2f}, немає цифр і посилань")

        # RF5 — число нижче плану, строк настав або захід постійний.
        due = (
            measure.deadline_type == "ongoing"
            or (measure.deadline_type == "date" and measure.deadline_on is not None and measure.deadline_on <= period_end)
        )
        if finished and due and execution.indicator_actual is not None and measure.indicator_target is not None:
            if Decimal(str(execution.indicator_actual)) < Decimal(str(measure.indicator_target)):
                add("RF5", "zakhid", measure.id,
                    f"факт {execution.indicator_actual} < ціль {measure.indicator_target}")

        # RF6 — не менше двох перенесень строку заходу.
        if deadline_by_measure[measure.id] >= 2:
            add("RF6", "zakhid", measure.id, f"строк переносили {deadline_by_measure[measure.id]} рази")

        # RF7a — фактична дата виконання пізніше за кінець періоду.
        if execution is not None and execution.completed_on is not None and execution.completed_on > period_end:
            add("RF7a", "zakhid", measure.id, f"фактична дата {execution.completed_on} після {period_end}")

        # RF7b — кожен доказ має дату після фактичного виконання.
        if (
            measure.deadline_type == "date" and execution is not None
            and execution.completed_on is not None and proof_orders
            and all(o.document_date is not None and o.document_date > execution.completed_on for o in proof_orders)
        ):
            first_date = min(o.document_date for o in proof_orders)
            add("RF7b", "zakhid", measure.id,
                f"найраніший документ {first_date}, виконання {execution.completed_on}")

        # RF7c — для стану «Не виконано» потрібна причина.
        if _report_not_completed(measure, execution, period_end) and not description:
            add("RF7c", "zakhid", measure.id, "стан «Не виконано», поле пояснення порожнє")

        # RF7e — стан «Строк не настав» із заповненим описом.
        if not_due and description:
            add("RF7e", "zakhid", measure.id, f"строк {measure.deadline_on}, опис уже заповнено")

    # RF6 — повторне прострочення у підрозділі (один сигнал на підрозділ).
    for department_id, ids in sorted(overdue_by_department.items()):
        if len(ids) >= 2:
            add("RF6", "pidrozdil", department_id, "прострочені заходи: " + ", ".join(sorted(ids)))

    # RF7d — ризик без заходів впливу (перевіряємо усі ризики).
    for risk in risks:
        if risk.level in _HIGH_RISK and risk.id not in measure_risk_ids:
            add("RF7d", "ryzyk", risk.id, f"рівень {risk.level}, заходів 0")

    signals.extend(detect_rf8_flags(
        period=period, as_of=as_of, measures=measures,
        invalid_order_attempts=invalid_order_attempts,
    ))
    return sorted(signals, key=lambda item: (item.code, item.object_type, item.object_id))
