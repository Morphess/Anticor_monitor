"""Перевірка на синтетичному наборі організаторів: система має знайти рівно ті сигнали, що в ключі,
і сформувати звіт, який збігається з еталонним звітом для Порталу."""
import csv
import json

from app.config import DATASET_DIR
from app.services import monitor


def test_import_counts(db):
    snap = monitor.snapshot()
    assert snap["period"] == "2026-H1"
    assert len(snap["measures"]) == 50
    assert len(snap["risks"]) == 14
    assert [s["code"] for s in snap["sections"]] == ["R1", "R2", "R3"]
    assert sum(len(m["evidence"]) for m in snap["measures"]) == 41


def test_flags_match_organizers_key(db):
    with open(DATASET_DIR / "kliuch" / "ochikuvani-sygnaly.csv", encoding="utf-8-sig", newline="") as f:
        expected = sorted((r["kod"], r["id"]) for r in csv.DictReader(f))
    found = sorted((f["code"], f["id"]) for f in monitor.snapshot()["flags"])
    assert len(expected) == 29
    assert found == expected


def test_report_matches_portal_etalon(db):
    etalon = json.loads((DATASET_DIR / "dani" / "nabir.json").read_text(encoding="utf-8"))["tablytsi"]["zvit_portal_2026_h1"]
    rows = monitor.portal_report(monitor.snapshot())
    assert len(rows) == len(etalon) == 50
    for ours, theirs in zip(rows, etalon):
        for key, value in theirs.items():
            assert str(ours[key]) == str("" if value is None else value), (theirs["zakhid_id"], key)


def test_risk_levels_match_dataset(db):
    risks = json.loads((DATASET_DIR / "dani" / "nabir.json").read_text(encoding="utf-8"))["tablytsi"]["ryzyky"]
    ours = {r["id"]: r for r in monitor.snapshot()["risks"]}
    for r in risks:
        assert ours[r["id"]]["level"] == r["riven"], r["id"]


def test_snapshot_is_deterministic(db):
    first, second = monitor.snapshot(), monitor.snapshot()
    assert first["flags"] == second["flags"]
    assert monitor.portal_report(first) == monitor.portal_report(second)
