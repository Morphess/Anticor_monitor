from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.risk import Risk
from app.models.department import Department

from app.repositories.risk_repository import RiskRepository
from app.schemas.risks import RiskBase, RiskCreate, RiskUpdate


class RiskError(Exception):

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


class RiskService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = RiskRepository(db)

    # READ - один ризик
    def get_risk(self, risk_id: str) -> Risk:

        risk = self.repo.get_by_id(risk_id)

        if risk is None:
            raise RiskError("Ризик не знайдено", 404)

        return risk

    # READ - список ризиків
    def list_risks(
        self, skip: int = 0, limit: int = 20, owner_department_id: str | None = None
    ) -> list[Risk]:

        return self.repo.list_risks(skip, limit, owner_department_id)

    # Перевірка підрозділу
    def check_department(self, department_id: str | None) -> None:

        if department_id is None:
            return

        department = self.db.get(Department, department_id)

        if department is None:
            raise RiskError("Підрозділ не існує")

    # CREATE
    def create_risk(self, data: RiskCreate) -> Risk:

        if self.repo.get_by_id(data.id):
            raise RiskError("Ризик із таким ID вже існує", 409)

        self.check_department(data.owner_department_id)

        risk = Risk(**data.model_dump())

        try:
            return self.repo.save(risk)

        except IntegrityError as error:
            self.db.rollback()
            raise RiskError("Помилка збереження ризику", 409) from error

    # UPDATE
    def update_risk(self, risk_id: str, data: RiskUpdate) -> Risk:

        risk = self.get_risk(risk_id)

        changes = data.model_dump(exclude_unset=True)

        required_fields = set(RiskBase.model_fields) - {"owner_department_id"}

        # Не дозволяємо очищати обов'язкові поля
        for field, value in changes.items():
            if field in required_fields and value is None:
                raise RiskError(f"Поле {field} не може бути null")

        # Поєднуємо старі та нові значення
        merged = {
            field: changes.get(field, getattr(risk, field))
            for field in RiskBase.model_fields
        }

        # Повна перевірка, зокрема правильності score
        try:
            validated = RiskBase.model_validate(merged)

        except ValidationError as error:
            raise RiskError("Некоректні дані або оцінка ризику", 422) from error

        self.check_department(validated.owner_department_id)

        # Оновлюємо змінені поля
        for field, value in changes.items():
            setattr(risk, field, value)

        try:
            return self.repo.save(risk)

        except IntegrityError as error:
            self.db.rollback()
            raise RiskError("Помилка оновлення ризику", 409) from error

    # DELETE
    def delete_risk(self, risk_id: str) -> None:

        risk = self.get_risk(risk_id)

        # Забороняємо видаляти ризик із пов'язаними даними
        if risk.measures or risk.measurements:
            raise RiskError("Ризик має пов'язані заходи або вимірювання", 409)

        try:
            self.repo.delete(risk)

        except IntegrityError as error:
            self.db.rollback()
            raise RiskError("Ризик має пов'язані записи", 409) from error
