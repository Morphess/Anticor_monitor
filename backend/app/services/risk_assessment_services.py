"""Історія переоцінок; окремо вимірювання і окремо підтверджена оцінка P×I."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.risk import Risk
from app.models.measure import Measure
from app.models.program_workflow import ProgramDepartment
from app.models.risk_assessment import RiskAssessment
from app.models.risk_measurement import RiskMeasurement
from app.models.department import Department
from app.models.user import User
from app.schemas.risk_assessments import AssessmentDraftCreate, MeasurementCreate
from app.services.department_hierarchy import DepartmentHierarchy, DepartmentHierarchyError


class AssessmentError(Exception):
    def __init__(self, code: int, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


class _DepartmentSource:
    def __init__(self, db: Session):
        self.db = db

    def all_departments(self):
        return list(self.db.scalars(select(Department)))


def risk_level(score: int) -> str:
    # Матриця 1–16 з Методології НАЗК 830/21; недосяжних балів 5,7,10,11 немає.
    if score >= 12:
        return "critical"
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def indicator_progress(risk: Risk, value: Decimal) -> Decimal | None:
    """Прогрес до цілі індикатора, НЕ відсоток зниження ризику."""
    baseline = Decimal(risk.indicator_baseline_value)
    target = Decimal(risk.indicator_target_value)
    if target == baseline:
        return None
    if risk.indicator_direction == "increase" and target < baseline:
        return None
    if risk.indicator_direction == "decrease" and target > baseline:
        return None
    return ((value - baseline) / (target - baseline) * 100).quantize(Decimal("0.01"))


class RiskAssessmentService:
    def __init__(self, db: Session):
        self.db = db

    def visible_risk(self, risk_id: str, actor: User, *, write: bool = False) -> Risk:
        risk = self.db.get(Risk, risk_id)
        if risk is None:
            raise AssessmentError(404, "Корупційний ризик не знайдено")
        if not actor.department_id:
            raise AssessmentError(403, "Користувачу не призначено підрозділ")
        if write:
            if actor.role_id != "MAIN_KOORD":
                raise AssessmentError(403, "Переоцінка доступна лише MAIN_KOORD")
            allowed = risk.owner_department_id == actor.department_id
        elif actor.role_id == "MAIN_KOORD":
            allowed = risk.owner_department_id == actor.department_id
        elif actor.role_id in {"KOORD", "KER"}:
            try:
                hierarchy = DepartmentHierarchy(_DepartmentSource(self.db))
                departments = hierarchy.descendants(actor.department_id)
                allowed = risk.owner_department_id in departments
                if not allowed:
                    # Ризик із реєстру MAIN_KOORD може бути прив'язаний до заходу
                    # програми, НАПРАВЛЕНОЇ підрозділу керівника/координатора.
                    # У цьому випадку показуємо лише історію ризику (без запису).
                    related_measure_id = self.db.scalar(
                        select(Measure.id)
                        .join(ProgramDepartment, ProgramDepartment.program_id == Measure.program_id)
                        .where(
                            Measure.risk_id == risk.id,
                            ProgramDepartment.department_id.in_(departments),
                        ).limit(1)
                    )
                    allowed = related_measure_id is not None
            except DepartmentHierarchyError as error:
                raise AssessmentError(409, str(error)) from error
        else:
            raise AssessmentError(403, "Недостатньо прав")
        if not allowed:
            raise AssessmentError(403, "Ризик поза доступною сферою підрозділу")
        return risk

    def _history(self, risk_id: str) -> list[RiskAssessment]:
        return list(self.db.scalars(
            select(RiskAssessment).where(RiskAssessment.risk_id == risk_id)
            .order_by(RiskAssessment.id)
        ).all())

    def _approved(self, risk_id: str) -> list[RiskAssessment]:
        return [x for x in self._history(risk_id) if x.status == "approved"]

    @staticmethod
    def _verify_current_rating(risk: Risk) -> None:
        score = risk.probability_score * risk.impact_score
        if risk.score != score or risk.level != risk_level(score):
            raise AssessmentError(
                409, "Поточні score/level у risks не узгоджені з P×I. "
                     "Виправте початкові дані перед створенням історії."
            )

    def register_measurement(self, risk_id: str, actor: User, data: MeasurementCreate):
        self.visible_risk(risk_id, actor, write=True)
        if data.measured_on > date.today():
            raise AssessmentError(422, "Дата вимірювання не може бути в майбутньому")
        if self.db.get(RiskMeasurement, (risk_id, data.measured_on)):
            raise AssessmentError(409, "Вимірювання на цю дату вже існує")
        measurement = RiskMeasurement(risk_id=risk_id, **data.model_dump())
        self.db.add(measurement)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise AssessmentError(409, "Не вдалося додати вимірювання") from error
        self.db.refresh(measurement)
        return measurement

    def ensure_baseline(self, risk_id: str, actor: User) -> RiskAssessment:
        risk = self.visible_risk(risk_id, actor, write=True)
        # Серіалізація конкуруючих змін за рядком risks (PostgreSQL).
        risk = self.db.scalar(select(Risk).where(Risk.id == risk.id).with_for_update())
        existing = self._approved(risk_id)
        if existing:
            baseline = next((x for x in existing if x.kind == "baseline"), None)
            if baseline is None:
                raise AssessmentError(409, "Не знайдено початкової оцінки")
            return baseline
        self._verify_current_rating(risk)
        baseline = RiskAssessment(
            risk_id=risk_id, kind="baseline", status="approved",
            assessed_on=date.today(), probability_score=risk.probability_score,
            impact_score=risk.impact_score, score=risk.score, level=risk.level,
            justification="Початковий знімок на дату ввімкнення модуля переоцінок; не ретроспективна оцінка.",
            created_by_user_id=actor.id, approved_by_user_id=actor.id,
            decided_at=datetime.now(timezone.utc),
        )
        self.db.add(baseline)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise AssessmentError(409, "Початкова оцінка вже зареєстрована") from error
        self.db.refresh(baseline)
        return baseline

    def create_draft(self, risk_id: str, actor: User, data: AssessmentDraftCreate):
        risk = self.visible_risk(risk_id, actor, write=True)
        if data.assessed_on > date.today() or data.measurement_on > data.assessed_on:
            raise AssessmentError(422, "Дати вимірювання й переоцінки некоректні")
        self.ensure_baseline(risk_id, actor)
        # Повторно блокуємо ризик після commit у ensure_baseline.
        risk = self.db.scalar(select(Risk).where(Risk.id == risk.id).with_for_update())
        if any(a.status == "draft" for a in self._history(risk_id)):
            raise AssessmentError(409, "У цього ризику вже є непідтверджена переоцінка")
        approved = self._approved(risk_id)
        if data.assessed_on < approved[-1].assessed_on:
            raise AssessmentError(422, "Дата переоцінки не може передувати останній підтвердженій")
        measurement = self.db.get(RiskMeasurement, (risk_id, data.measurement_on))
        if measurement is None:
            raise AssessmentError(422, "Спочатку внесіть реальне вимірювання індикатора")
        score = data.probability_score * data.impact_score
        draft = RiskAssessment(
            risk_id=risk_id, kind="reassessment", status="draft",
            assessed_on=data.assessed_on,
            probability_score=data.probability_score,
            impact_score=data.impact_score,
            score=score, level=risk_level(score),
            measurement_on=data.measurement_on,
            measurement_value=measurement.value,
            measurement_source=measurement.source,
            justification=data.justification,
            created_by_user_id=actor.id,
        )
        self.db.add(draft)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise AssessmentError(409, "Конфлікт створення переоцінки") from error
        self.db.refresh(draft)
        return draft

    def _pending(self, risk_id: str, id: int, actor: User):
        risk = self.visible_risk(risk_id, actor, write=True)
        risk = self.db.scalar(select(Risk).where(Risk.id == risk.id).with_for_update())
        draft = self.db.get(RiskAssessment, id)
        if draft is None or draft.risk_id != risk_id:
            raise AssessmentError(404, "Переоцінку не знайдено")
        if draft.status != "draft":
            raise AssessmentError(409, "Рішення щодо цієї переоцінки вже прийнято")
        approved = self._approved(risk_id)
        if not approved or draft.assessed_on < approved[-1].assessed_on:
            raise AssessmentError(409, "Переоцінка застаріла або немає початкової оцінки")
        last = approved[-1]
        if (risk.score, risk.probability_score, risk.impact_score, risk.level) != (
            last.score, last.probability_score, last.impact_score, last.level
        ):
            raise AssessmentError(409, "Ризик змінено поза журналом переоцінок")
        return risk, draft

    def approve(self, risk_id: str, id: int, actor: User, reason: str):
        risk, draft = self._pending(risk_id, id, actor)
        draft.status = "approved"
        draft.approved_by_user_id = actor.id
        draft.decided_at = datetime.now(timezone.utc)
        draft.decision_reason = reason
        risk.probability_score = draft.probability_score
        risk.impact_score = draft.impact_score
        risk.score = draft.score
        risk.level = draft.level
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def reject(self, risk_id: str, id: int, actor: User, reason: str):
        _, draft = self._pending(risk_id, id, actor)
        draft.status = "rejected"
        draft.approved_by_user_id = actor.id
        draft.decided_at = datetime.now(timezone.utc)
        draft.decision_reason = reason
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def history(self, risk_id: str, actor: User):
        self.visible_risk(risk_id, actor)
        return self._history(risk_id)

    def trend(self, risk_id: str, actor: User):
        risk = self.visible_risk(risk_id, actor)
        history = self._history(risk_id)
        approved = [x for x in history if x.status == "approved"]
        baseline = next((x for x in approved if x.kind == "baseline"), None)
        reassessments = [x for x in approved if x.kind == "reassessment"]
        if not reassessments:
            delta, direction = None, "not_reassessed"
        else:
            # Динаміка щодо ПОПЕРЕДНЬОЇ затвердженої оцінки; baseline окремо.
            previous = approved[-2]
            delta = approved[-1].score - previous.score
            direction = "decreasing" if delta < 0 else "increasing" if delta > 0 else "stable"
        measurements = list(self.db.scalars(
            select(RiskMeasurement).where(
                RiskMeasurement.risk_id == risk_id,
                RiskMeasurement.measured_on <= date.today(),
            )
            .order_by(RiskMeasurement.measured_on)
        ))
        latest = measurements[-1] if measurements else None
        values = [Decimal(m.value) for m in measurements[-3:]]
        worsened_twice = len(values) == 3 and (
            (values[0] < values[1] < values[2]) if risk.indicator_direction == "decrease"
            else (values[0] > values[1] > values[2])
        )
        return {
            "risk_id": risk.id, "risk_title": risk.title,
            "baseline_score": baseline.score if baseline else None,
            "current_score": risk.score, "delta_score": delta,
            "trend": direction, "current_level": risk.level,
            "latest_measurement_on": latest.measured_on if latest else None,
            "latest_measurement_value": latest.value if latest else None,
            "indicator_progress_percent": indicator_progress(risk, latest.value) if latest else None,
            "indicator_worsened_twice": worsened_twice,
            "history": history,
        }
