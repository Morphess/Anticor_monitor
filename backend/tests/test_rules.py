"""Чисті правила: без бази, годинника й випадковості."""
from datetime import date

import pytest

from app.services import rules
from app.services.rules import WorkflowError

H1_END = date(2026, 6, 30)


def measure(**over):
    m = {"id": "Z-99", "section": "R2", "content": "Провести перевірку договорів", "deadline_type": "data",
         "deadline_date": date(2026, 3, 31), "indicator_target": 10, "indicator_unit": "од.",
         "status": "vykonano", "actual_date": date(2026, 3, 20),
         "result_text": "Перевірено 10 договорів, акт № 5 від 20.03.2026.", "indicator_fact": 10,
         "evidence_dates": [date(2026, 3, 20)], "risk": {"id": "KR01", "base": 20, "current": 8, "target": 5},
         "postponements": 0}
    return {**m, **over}


def codes(m):
    return [c for c, _ in rules.measure_flags(m, H1_END)]


def test_clean_measure_has_no_flags():
    assert codes(measure()) == []


@pytest.mark.parametrize("score,level", [(1, "низький"), (2, "низький"), (3, "середній"), (4, "середній"),
                                         (6, "високий"), (9, "високий"), (12, "критичний"), (16, "критичний")])
def test_risk_level(score, level):
    assert rules.risk_level(score) == level


def test_risk_progress():
    assert rules.risk_progress(20, 5, 5) == 1
    assert rules.risk_progress(20, 20, 5) == 0
    assert round(rules.risk_progress(20, 12.5, 5), 2) == 0.5
    assert round(rules.risk_progress(40, 70, 100), 2) == 0.5      # індикатор, що має зростати


def test_portal_state():
    assert rules.portal_state("vykonano", "data", date(2026, 3, 1), H1_END) == rules.PORTAL_DONE
    assert rules.portal_state("chastkovo", "data", date(2026, 3, 1), H1_END) == rules.PORTAL_PARTIAL
    assert rules.portal_state("v_roboti", "data", date(2026, 9, 1), H1_END) == rules.PORTAL_NOT_DUE
    assert rules.portal_state("v_roboti", "data", date(2026, 3, 1), H1_END) == rules.PORTAL_NOT_DONE
    assert rules.portal_state("ne_rozpochato", "postiino", None, H1_END) == rules.PORTAL_NOT_DONE


def test_rf1_overdue():
    assert "RF1" in codes(measure(status="v_roboti", actual_date=None, evidence_dates=[]))
    assert "RF1" not in codes(measure(status="v_roboti", deadline_date=date(2026, 9, 30), actual_date=None))


def test_rf2_no_evidence():
    assert "RF2" in codes(measure(evidence_dates=[]))


def test_rf3_formal_closure_only_for_section_two():
    stuck = {"id": "KR01", "base": 20, "current": 19.5, "target": 5}
    assert "RF3" in codes(measure(risk=stuck))
    assert "RF3" not in codes(measure(risk=stuck, section="R1"))
    assert "RF3" not in codes(measure(risk=stuck, status="chastkovo"))


def test_rf4_result_repeats_content():
    assert "RF4" in codes(measure(result_text="Проведено перевірку договорів"))
    assert "RF4" not in codes(measure(result_text="Проведено перевірку 10 договорів"))


def test_rf5_indicator_below_target():
    assert "RF5" in codes(measure(indicator_fact=6))


def test_rf6_repeated_postponements_and_unit():
    assert "RF6" in codes(measure(postponements=2))
    assert "RF6" not in codes(measure(postponements=1))
    assert [u for u, _, _ in rules.unit_flags({"P01": ["Z-01", "Z-02"], "P02": ["Z-03"]})] == ["P01"]


def test_rf7_data_quality():
    assert "RF7a" in codes(measure(actual_date=date(2026, 7, 2), evidence_dates=[date(2026, 7, 2)]))
    assert "RF7b" in codes(measure(evidence_dates=[date(2026, 4, 15)]))
    assert "RF7c" in codes(measure(status="ne_vykonano", actual_date=None, result_text="", evidence_dates=[]))
    assert "RF7e" in codes(measure(status="v_roboti", deadline_date=date(2026, 9, 30), actual_date=None,
                                   result_text="Готуємо проєкт наказу"))
    assert rules.risk_flags("KR09", "високий", 0)[0][0] == "RF7d"
    assert rules.risk_flags("KR09", "середній", 0) == []
    assert rules.risk_flags("KR09", "критичний", 2) == []


def test_flags_are_deterministic_and_explained():
    m = measure(evidence_dates=[], indicator_fact=6)
    first = rules.measure_flags(m, H1_END)
    assert first == rules.measure_flags(dict(m), H1_END)
    assert all(why.strip() for _, why in first)


def test_review_transitions():
    assert rules.next_review_state("draft", "submit", "VYK") == "submitted"
    assert rules.next_review_state("submitted", "approve", "KOORD") == "approved"
    assert rules.next_review_state("submitted", "return", "KOORD") == "returned"
    assert rules.next_review_state("returned", "submit", "VYK") == "submitted"
    for state, action, role in [("submitted", "save", "VYK"), ("approved", "submit", "VYK"),
                                ("draft", "approve", "KOORD"), ("approved", "return", "KOORD"),
                                ("submitted", "approve", "VYK"), ("draft", "submit", "KOORD"),
                                ("submitted", "approve", "KER"), ("submitted", "approve", "ADMIN")]:
        with pytest.raises(WorkflowError):
            rules.next_review_state(state, action, role)


def test_submission_checks():
    today = date(2026, 7, 6)
    rules.check_submission("v_roboti", "", None, today)
    with pytest.raises(WorkflowError):
        rules.check_submission("vykonano", "  ", None, today)
    with pytest.raises(WorkflowError):
        rules.check_submission("vykonano", "Зроблено", date(2026, 8, 1), today)
    with pytest.raises(WorkflowError):
        rules.check_return(" ")


def test_reminders():
    today = date(2026, 7, 6)
    assert rules.due_soon("v_roboti", "data", date(2026, 7, 31), today)
    assert not rules.due_soon("vykonano", "data", date(2026, 7, 31), today)
    assert not rules.due_soon("v_roboti", "data", date(2026, 9, 30), today)
    assert rules.overdue_today("v_roboti", "data", date(2026, 6, 30), today)
    assert not rules.overdue_today("v_roboti", "postiino", None, today)
