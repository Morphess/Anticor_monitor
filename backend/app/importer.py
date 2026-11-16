"""Імпорт синтетичного набору організаторів (data/nabir-orhanizatoriv/dani/nabir.json) у базу.

Запуск вручну (таблиці перестворюються, усі дані видаляються):
    cd backend && python -m app.importer
Якщо база порожня, імпорт виконується автоматично під час запуску застосунку (AUTO_IMPORT=1).
"""
import json
from datetime import date, datetime

from .config import DATASET_DIR
from .db import init_db, session, session_scope
from .models import (DeadlineChange, Evidence, Execution, JournalEntry, Measure, Program, Risk, RiskMeasurement,
                     Section, Setting, Unit, User)
from .utils import TZ


def _d(value) -> date | None:
    return date.fromisoformat(value) if value else None


def _dt(value) -> datetime | None:
    """Час у наборі — місцевий (київський) без поясу."""
    return datetime.fromisoformat(value).replace(tzinfo=TZ) if value else None


def _num(value) -> float | None:
    return None if value in ("", None) else float(value)


def import_dataset(reset: bool = True) -> dict:
    """Завантажує набір у базу у власній сесії. reset=True — спершу перестворює всі таблиці."""
    with session_scope():
        return _import(reset)


def _import(reset: bool) -> dict:
    data = json.loads((DATASET_DIR / "dani" / "nabir.json").read_text(encoding="utf-8"))
    meta, t = data["meta"], data["tablytsi"]
    s = session()
    s.commit()              # звільнити блокування поточної транзакції перед перебудовою таблиць
    init_db(drop=reset)

    for r in t["pidrozdily"]:
        s.add(Unit(id=r["id"], name=r["nazva"], type=r["typ"], note=r["prymitka"]))
    s.flush()
    for r in t["korystuvachi"]:
        s.add(User(id=r["id"], role=r["rol"], unit_id=r["pidrozdil_id"] or None, position=r["posada"]))
    for r in t["rozdily"]:
        s.add(Section(code=r["kod"], number=r["nomer"], title=r["nazva_portal"]))
    p = t["prohrama"][0]
    s.add(Program(id=p["id"], name=p["nazva"], organ=p["organ"], period_start=_d(p["period_pochatok"]),
                  period_end=_d(p["period_kinets"]), approved_by=p["zatverdzheno"],
                  nazk_status=p["stan_pohodzhennia_nazk"],
                  restricted=p["mistyt_informatsiiu_z_obmezhenym_dostupom"] == "так",
                  authorized_unit_id=p["upovnovazhenyi_pidrozdil_id"], goals=p["tsili"], note=p["prymitka"]))
    s.flush()

    for r in t["ryzyky"]:
        s.add(Risk(id=r["id"], function=r["funktsiia_protses"], name=r["nazva"], content=r["zmist"],
                   sources=r["dzherela"], existing_controls=r["isnuiuchi_zakhody_kontroliu"],
                   probability=r["imovirnist_x"], impact=r["naslidky_y"], owner_unit_id=r["vlasnyk_pidrozdil_id"],
                   indicator_name=r["indykator_ryzyku"], indicator_unit=r["odynytsia"], direction=r["napriam"],
                   indicator_base=float(r["indykator_bazove"]), indicator_target=float(r["indykator_tsil"]),
                   target_date=_d(r["data_tsili"])))
    s.flush()
    for r in t["vymiriuvannia_indykatoriv"]:
        s.add(RiskMeasurement(risk_id=r["ryzyk_id"], date=_d(r["data"]), value=float(r["znachennia"]),
                              source=r["dzherelo"]))

    for r in t["zakhody"]:
        s.add(Measure(id=r["id"], section_code=r["rozdil_kod"], number=r["nomer_u_rozdili"], content=r["zmist"],
                      risk_id=r["ryzyk_id"] or None, unit_id=r["vidpovidalnyi_pidrozdil_id"],
                      co_units=[x.strip() for x in r["spivvykonavtsi"].split(";") if x.strip()],
                      executor_id=r["vykonavets_korystuvach_id"] or None, deadline_text=r["strok_tekst"],
                      deadline_type=r["strok_typ"], deadline_date=_d(r["strok_data"]),
                      indicator_name=r["indykator_vykonannia"], indicator_unit=r["indykator_odynytsia"],
                      indicator_target=_num(r["indykator_tsil"]), required_evidence=r["potribni_pidtverdzhennia"],
                      resources=r["resursy"]))
    s.flush()

    # Час погодження координатором беремо з журналу набору
    approved_at = {j["obiekt_id"]: _dt(j["chas"]) for j in t["zhurnal_dii"] if j["diia"] == "погоджено координатором"}
    coordinator = next(u["id"] for u in t["korystuvachi"] if u["rol"] == "KOORD")
    for r in t["vykonannia_2026_h1"]:
        approved = r["pohodzheno_koordynatorom"] == "так"
        entered = _dt(r["data_vnesennia"])
        s.add(Execution(measure_id=r["zakhid_id"], period=r["period"], status=r["status"],
                        actual_date=_d(r["fakt_data"]), result_text=r["opys_rezultatu"],
                        indicator_fact=_num(r["indykator_fakt"]), entered_by_id=r["vnis_korystuvach_id"] or None,
                        entered_at=entered,
                        review_state="approved" if approved else ("submitted" if entered else "draft"),
                        reviewed_by_id=coordinator if approved else None,
                        reviewed_at=approved_at.get(r["zakhid_id"]) if approved else None))

    for r in t["pidtverdzhennia"]:
        s.add(Evidence(id=r["id"], measure_id=r["zakhid_id"], type=r["typ"], name=r["nazva"],
                       doc_date=_d(r["data_dokumenta"]), link=r["posylannia"], uploaded_at=_dt(r["zavantazheno"]),
                       uploaded_by_id=r["zavantazhyv_korystuvach_id"], sha256=r["sha256"]))
    for r in t["perenesennia_strokiv"]:
        s.add(DeadlineChange(measure_id=r["zakhid_id"], decision_date=_d(r["data_rishennia"]),
                             old_date=_d(r["staryi_strok"]), new_date=_d(r["novyi_strok"]), reason=r["prychyna"],
                             approved_by_id=r["pohodyv_korystuvach_id"]))
    for r in t["zhurnal_dii"]:
        s.add(JournalEntry(at=_dt(r["chas"]), user_id=r["korystuvach_id"], action=r["diia"], object=r["obiekt"],
                           object_id=r["obiekt_id"], field=r["pole"], old_value=r["stare_znachennia"],
                           new_value=r["nove_znachennia"]))

    # Звітний період і дата зрізу даних — із метаданих набору
    s.add(Setting(key="period", value={"value": meta["period"]}))
    s.add(Setting(key="as_of", value={"value": meta["data_zrizu"]}))
    s.commit()
    counts = {k: len(v) for k, v in t.items()}
    print(f"Набір організаторів імпортовано: заходів {counts['zakhody']}, ризиків {counts['ryzyky']}, "
          f"підрозділів {counts['pidrozdily']}, користувачів {counts['korystuvachi']}, "
          f"підтверджень {counts['pidtverdzhennia']}, записів журналу {counts['zhurnal_dii']}. "
          f"Період {meta['period']}, дата зрізу {meta['data_zrizu']}.")
    return counts


if __name__ == "__main__":
    import_dataset()
