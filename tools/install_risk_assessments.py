"""Точкове підключення Risk Assessments. Запускати з кореня Anticor_monitor.

python tools/install_risk_assessments.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "backend" / "app"


def patch(path: Path, original: str, replacement: str):
    if not path.exists():
        raise RuntimeError(f"Не знайдено {path}")
    data = path.read_text(encoding="utf-8")
    if replacement in data:
        print("[OK] Раніше встановлено:", path.relative_to(ROOT))
        return
    if data.count(original) != 1:
        raise RuntimeError(f"Не знайдено однозначне місце для вставки у {path}")
    backup = path.with_suffix(path.suffix + ".bak-rad-" + datetime.now().strftime("%Y%m%d%H%M%S%f"))
    shutil.copy2(path, backup)
    path.write_text(data.replace(original, replacement), encoding="utf-8")
    print("[PATCH]", path.relative_to(ROOT), "(резервна копія:", backup.name, ")")


def main():
    if not APP.exists():
        raise RuntimeError("Запусти з кореня Anticor_monitor: має існувати backend/app")
    models = APP / "models" / "__init__.py"
    main = APP / "main.py"
    risks = APP / "api" / "risks.py"
    schema = APP / "schemas" / "risks.py"

    # Заздалегідь перевіряємо форму ключових файлів, щоб не зробити напівпатч.
    assert "from .risk import Risk" in models.read_text(encoding="utf-8"), "Незнайома models/__init__.py"
    assert "from app.api.risks import router as risks_router" in main.read_text(encoding="utf-8"), "Незнайома main.py"
    assert "def update_risk(" in risks.read_text(encoding="utf-8"), "Незнайома api/risks.py"
    assert "class RiskBase(BaseModel):" in schema.read_text(encoding="utf-8"), "Незнайома schemas/risks.py"

    # Усі фрагменти перевіряємо ДО першого запису, щоб не отримати напівпатч.
    risk_update_original = "    _owned(db, risk_id, actor)\n    try:\n        return RiskService(db).update_risk(risk_id, data)"
    risk_update_new = (
        "    _owned(db, risk_id, actor)\n"
        "    if {'probability_score', 'impact_score', 'score', 'level'} & data.model_fields_set:\n"
        "        raise HTTPException(409, detail='Оцінка ризику змінюється лише через /risk-assessments/{risk_id}/drafts')\n"
        "    try:\n        return RiskService(db).update_risk(risk_id, data)"
    )
    base_validator_original = (
        '        if self.score != expected_score:\n'
        '            raise ValueError(\n'
        '                f"Неправильний бал ризику. " f"Очікується {expected_score}"\n'
        '            )\n\n'
        '        return self'
    )
    base_validator_new = (
        '        if self.score != expected_score:\n'
        '            raise ValueError(\n'
        '                f"Неправильний бал ризику. " f"Очікується {expected_score}"\n'
        '            )\n\n'
        '        from app.services.risk_assessment_services import risk_level\n'
        '        if self.level != risk_level(expected_score):\n'
        "            raise ValueError('Рівень ризику не відповідає P × I')\n\n"
        '        return self'
    )
    steps = [
        (models,
         'from .risk import Risk\n',
         'from .risk import Risk\nfrom .risk_assessment import RiskAssessment\n'),
        (main,
         'from app.api.risks import router as risks_router\n',
         'from app.api.risks import router as risks_router\n'
         'from app.api.risk_assessments import router as risk_assessments_router\n'),
        (main,
         'app.include_router(risks_router, prefix="/api")\n',
         'app.include_router(risks_router, prefix="/api")\n'
         'app.include_router(risk_assessments_router, prefix="/api")\n'),
        (risks, risk_update_original, risk_update_new),
        (schema, base_validator_original, base_validator_new),
    ]
    for path, old, revised in steps:
        contents = path.read_text(encoding="utf-8")
        if revised not in contents and contents.count(old) != 1:
            raise RuntimeError(
                f"Версія файлу {path.relative_to(ROOT)} відрізняється від "
                "перевіреної. Нічого не змінено; потрібне ручне узгодження патчу."
            )
    for path, old, revised in steps:
        patch(path, old, revised)
    print("\nГотово. Далі: cd backend && alembic upgrade head")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, AssertionError) as error:
        print("[STOP]", error, file=sys.stderr)
        raise SystemExit(1)
