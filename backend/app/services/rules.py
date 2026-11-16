"""Правила, за якими система ухвалює висновки.

Усі функції ЧИСТІ: не звертаються до бази, не читають годинник, не використовують випадковість чи ШІ.
Результат залежить лише від аргументів, тому за однакових вхідних даних висновок завжди однаковий,
а кожен сигнал повертається разом із поясненням — на яких значеннях він спрацював.

Джерела правил:
  • рівень ризику — Методологія НАЗК № 830/21 (розд. III, гл. 6);
  • стан і фактичний строк у звіті — Роз'яснення НАЗК № 3 від 07.10.2026 (структура Порталу доброчесності);
  • сигнали RF1–RF7e — правила організаторів (data/nabir-orhanizatoriv/dictionary.md).
Тести (tests/test_dataset.py) перевіряють, що на наборі організаторів ці правила дають рівно 29 сигналів
із ключа і звіт, який збігається з еталонним.
"""
import re
from dataclasses import dataclass
from datetime import date


class WorkflowError(Exception):
    """Дію не можна виконати — текст показується користувачу."""


# ---------- Довідники ----------
STATUS_LABELS = {              # стан виконання, який заявляє виконавець
    "ne_rozpochato": "не розпочато",
    "v_roboti": "у роботі",
    "chastkovo": "частково виконано",
    "vykonano": "виконано",
    "ne_vykonano": "не виконано",
}
REVIEW_LABELS = {              # етап погодження координатором
    "draft": "не подано",
    "submitted": "на погодженні",
    "returned": "повернуто на доопрацювання",
    "approved": "погоджено",
}
DEADLINE_TYPES = {"data": "до дати", "postiino": "постійно", "periodychno": "періодично"}
ROLES = {"ADMIN": "Адміністратор", "KOORD": "Координатор програми", "VYK": "Виконавець",
         "KER": "Керівник", "ANAL": "Аналітик"}

# Значення спадного списку «Стан виконання» на Порталі доброчесності
PORTAL_DONE = "Виконано"
PORTAL_PARTIAL = "Частково виконано"
PORTAL_NOT_DONE = "Не виконано"
PORTAL_NOT_DUE = "Строк виконання заходу не настав"
PORTAL_STATES = (PORTAL_DONE, PORTAL_NOT_DONE, PORTAL_PARTIAL, PORTAL_NOT_DUE)

FORMAL_CLOSURE_THRESHOLD = 0.10   # RF3: частка шляху від базового до цільового значення індикатора ризику
SIMILARITY_THRESHOLD = 0.6        # RF4: поріг подібності опису результату до змісту заходу
DUE_SOON_DAYS = 30                # нагадування: до строку залишилося не більше стількох днів


# ---------- Ризик (Методологія НАЗК № 830/21) ----------
def risk_score(probability: int, impact: int) -> int:
    return probability * impact


def risk_level(score: int) -> str:
    if score >= 12:
        return "критичний"
    if score >= 6:
        return "високий"
    if score >= 3:
        return "середній"
    return "низький"


def risk_progress(base: float, current: float, target: float) -> float:
    """Яку частку шляху від базового до цільового значення пройшов індикатор стану ризику.
    0 — не змінився, 1 — ціль досягнуто, від'ємне — погіршився. Працює для обох напрямів (менше / більше)."""
    gap = target - base
    return (current - base) / gap if gap else 1.0


# ---------- Звіт у структурі Порталу доброчесності ----------
def deadline_not_due(deadline_type: str, deadline_date: date | None, period_end: date) -> bool:
    return deadline_type == "data" and deadline_date is not None and deadline_date > period_end


def portal_state(status: str, deadline_type: str, deadline_date: date | None, period_end: date) -> str:
    """«Стан виконання» для Порталу."""
    if deadline_not_due(deadline_type, deadline_date, period_end) and status != "vykonano":
        return PORTAL_NOT_DUE
    return {"vykonano": PORTAL_DONE, "chastkovo": PORTAL_PARTIAL}.get(status, PORTAL_NOT_DONE)


def portal_actual_date(status: str, deadline_type: str, actual_date: date | None, period_end: date) -> date | None:
    """«Фактичний строк виконання»: для постійних і періодичних заходів — кінцева дата півріччя;
    для виконаного заходу з датою — фактична дата; інакше порожньо (відкрите питання Роз'яснення № 3)."""
    if deadline_type in ("postiino", "periodychno"):
        return period_end
    if status == "vykonano" and actual_date:
        return actual_date
    return None


def portal_description(state: str, result_text: str) -> str:
    """«Опис результату… або пояснення причин невиконання»: для заходу, строк якого не настав, не заповнюється."""
    return "" if state == PORTAL_NOT_DUE else (result_text or "")


# ---------- Подібність текстів (RF4) ----------
_WORD_RE = re.compile(r"[а-щьюяґєіїʼ'a-z]+")


def stems(text: str) -> set[str]:
    """Множина перших п'яти літер слів довжиною від 4 літер."""
    return {w[:5] for w in _WORD_RE.findall((text or "").lower()) if len(w) >= 4}


def similarity(a: str, b: str) -> float:
    """Коефіцієнт Жаккара на множинах stems()."""
    sa, sb = stems(a), stems(b)
    return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


# ---------- Сигнали Risk Flags ----------
@dataclass(frozen=True)
class FlagRule:
    code: str
    title: str
    rule: str      # явне правило
    obj: str       # до чого застосовується


FLAG_RULES = (
    FlagRule("RF1", "Прострочений захід: строк за програмою минув, захід не виконано",
             "Строк заходу — конкретна дата не пізніше кінця звітного періоду, а стан виконання не «виконано».",
             "захід"),
    FlagRule("RF2", "Немає підтвердних матеріалів для заходу зі станом «виконано» або «частково виконано»",
             "Стан «виконано» або «частково виконано», а підтвердних матеріалів — 0.", "захід"),
    FlagRule("RF3", "Формальне закриття: захід другого розділу виконано, але індикатор пов'язаного ризику "
                    "майже не змінився",
             "Захід розділу «Заходи з усунення корупційних ризиків» має стан «виконано», а індикатор стану "
             "його ризику пройшов менше 10 % шляху від базового до цільового значення.", "захід"),
    FlagRule("RF4", "Опис результату повторює зміст заходу і не містить вимірюваного показника чи посилання",
             "Стан «виконано» або «частково виконано»; в описі немає цифр і посилань; подібність опису до змісту "
             "заходу не менша за 0,6 (коефіцієнт Жаккара на перших п'яти літерах слів від 4 літер).", "захід"),
    FlagRule("RF5", "Показник не досягнуто: фактичне значення індикатора виконання нижче цільового",
             "Стан «виконано» або «частково виконано», строк настав (або захід постійний чи періодичний), "
             "фактичне значення індикатора менше за цільове.", "захід"),
    FlagRule("RF6", "Повторні порушення строків",
             "Строк заходу переносили двічі і більше, або в підрозділі два і більше прострочених заходи (RF1).",
             "захід, підрозділ"),
    FlagRule("RF7a", "Фактична дата виконання поза звітним періодом",
             "Фактична дата виконання пізніша за кінець звітного періоду.", "захід"),
    FlagRule("RF7b", "Підтвердження «заднім числом»",
             "Захід із конкретним строком має фактичну дату, і всі його підтвердні документи датовано "
             "пізніше за неї: на дату закриття підтвердження не було.", "захід"),
    FlagRule("RF7c", "Захід не виконано, а пояснення причин немає",
             "Стан для Порталу — «Не виконано», а поле опису порожнє (на Порталі воно обов'язкове).", "захід"),
    FlagRule("RF7d", "Ризик високого або критичного рівня без жодного заходу впливу",
             "Рівень ризику «високий» або «критичний», а заходів, пов'язаних із ним, — 0.", "ризик"),
    FlagRule("RF7e", "Опис заповнено для заходу, строк якого не настав",
             "Стан для Порталу — «Строк виконання заходу не настав», а опис заповнено "
             "(на Порталі такий опис не заповнюється).", "захід"),
)
FLAG_BY_CODE = {f.code: f for f in FLAG_RULES}


def _pct(x: float) -> str:
    return f"{x:.0%}"


def measure_flags(m: dict, period_end: date) -> list[tuple[str, str]]:
    """Сигнали щодо одного заходу: [(код, пояснення з конкретними значеннями)].

    m — словник із полями:
      id, section ('R1'|'R2'|'R3'), content, deadline_type, deadline_date (date|None),
      indicator_target (float|None), indicator_unit,
      status, actual_date (date|None), result_text, indicator_fact (float|None),
      evidence_dates (list[date]) — дати підтвердних документів,
      risk (None або {id, base, current, target}) — індикатор стану пов'язаного ризику,
      postponements (int) — скільки разів переносили строк.
    """
    out: list[tuple[str, str]] = []
    st, text = m["status"], m.get("result_text") or ""
    dtype, ddate = m["deadline_type"], m.get("deadline_date")
    label = STATUS_LABELS.get(st, st)

    if dtype == "data" and ddate and ddate <= period_end and st != "vykonano":
        out.append(("RF1", f"строк {ddate.isoformat()}, стан «{label}»"))

    if st in ("vykonano", "chastkovo") and not m.get("evidence_dates"):
        out.append(("RF2", "підтвердних матеріалів: 0"))

    risk = m.get("risk")
    if m["section"] == "R2" and st == "vykonano" and risk:
        progress = risk_progress(risk["base"], risk["current"], risk["target"])
        if progress < FORMAL_CLOSURE_THRESHOLD:
            out.append(("RF3", f"ризик {risk['id']}: {_n(risk['base'])} → {_n(risk['current'])} при цілі "
                               f"{_n(risk['target'])} (пройдено {_pct(progress)} шляху)"))

    if st in ("vykonano", "chastkovo") and text and not re.search(r"\d", text) and "http" not in text:
        sim = similarity(text, m["content"])
        if sim >= SIMILARITY_THRESHOLD:
            out.append(("RF4", f"подібність опису до змісту {sim:.2f}, чисел і посилань немає"))

    target, fact = m.get("indicator_target"), m.get("indicator_fact")
    if st in ("vykonano", "chastkovo") and target is not None and fact is not None:
        due = dtype != "data" or (ddate is not None and ddate <= period_end)
        if due and fact < target:
            out.append(("RF5", f"індикатор {_n(fact)} при цілі {_n(target)} {m.get('indicator_unit') or ''}".rstrip()
                               + f", стан «{label}»"))

    actual = m.get("actual_date")
    if actual and actual > period_end:
        out.append(("RF7a", f"фактична дата {actual.isoformat()} після {period_end.isoformat()}"))

    dates = m.get("evidence_dates") or []
    if dtype == "data" and actual and dates and all(d > actual for d in dates):
        out.append(("RF7b", f"найраніший документ від {min(dates).isoformat()} при фактичній даті {actual.isoformat()}"))

    state = portal_state(st, dtype, ddate, period_end)
    if state == PORTAL_NOT_DONE and not text:
        out.append(("RF7c", "поле «Опис результату… або пояснення причин невиконання» порожнє"))
    if state == PORTAL_NOT_DUE and text:
        out.append(("RF7e", f"строк {ddate.isoformat()}, опис заповнено"))

    if m.get("postponements", 0) >= 2:
        out.append(("RF6", f"строк переносили {m['postponements']} рази"))
    return out


def unit_flags(overdue_by_unit: dict[str, list[str]]) -> list[tuple[str, str, str]]:
    """RF6 для підрозділів: [(id підрозділу, 'RF6', пояснення)] — два і більше прострочених заходи."""
    return [(unit, "RF6", f"прострочені заходи: {', '.join(ids)}")
            for unit, ids in sorted(overdue_by_unit.items()) if len(ids) >= 2]


def risk_flags(risk_id: str, level: str, measures_count: int) -> list[tuple[str, str]]:
    """RF7d для ризику."""
    if measures_count == 0 and level in ("високий", "критичний"):
        return [("RF7d", f"рівень «{level}», заходів 0")]
    return []


def _n(x) -> str:
    f = float(x)
    return str(int(f)) if f == int(f) else f"{f:g}"


# ---------- Нагадування про строки ----------
def due_soon(status: str, deadline_type: str, deadline_date: date | None, today: date,
             days: int = DUE_SOON_DAYS) -> bool:
    """Наближається строк: до конкретної дати залишилося 0–days днів, а захід не виконано."""
    return (deadline_type == "data" and deadline_date is not None and status != "vykonano"
            and 0 <= (deadline_date - today).days <= days)


def overdue_today(status: str, deadline_type: str, deadline_date: date | None, today: date) -> bool:
    """Строк уже минув (на сьогоднішню дату), а захід не виконано."""
    return deadline_type == "data" and deadline_date is not None and status != "vykonano" and deadline_date < today


# ---------- Процес внесення й погодження ----------
# (етап погодження, дія) -> новий етап. Інших переходів не існує.
REVIEW_TRANSITIONS = {
    ("draft", "save"): "draft",
    ("returned", "save"): "returned",
    ("draft", "submit"): "submitted",
    ("returned", "submit"): "submitted",
    ("submitted", "approve"): "approved",
    ("submitted", "return"): "returned",
}
ACTION_ROLE = {"save": "VYK", "submit": "VYK", "approve": "KOORD", "return": "KOORD"}
EDITABLE_STATES = ("draft", "returned")


def next_review_state(state: str, action: str, role: str) -> str:
    if ACTION_ROLE.get(action) != role:
        raise WorkflowError("Ця дія недоступна для вашої ролі")
    try:
        return REVIEW_TRANSITIONS[(state, action)]
    except KeyError:
        if action in ("save", "submit"):
            raise WorkflowError("Інформацію вже подано на погодження або погоджено — редагування недоступне")
        raise WorkflowError("Рішення можна прийняти лише щодо інформації, поданої на погодження")


def check_submission(status: str, result_text: str, actual_date: date | None, today: date) -> None:
    """Що має бути заповнено перед поданням на погодження."""
    if status not in STATUS_LABELS:
        raise WorkflowError("Оберіть стан виконання")
    if status in ("vykonano", "chastkovo", "ne_vykonano") and not (result_text or "").strip():
        raise WorkflowError("Опишіть результат виконання або причини невиконання")
    if actual_date and actual_date > today:
        raise WorkflowError("Фактична дата виконання не може бути в майбутньому")


def check_return(comment: str) -> None:
    if not (comment or "").strip():
        raise WorkflowError("Вкажіть, що саме треба доопрацювати")
