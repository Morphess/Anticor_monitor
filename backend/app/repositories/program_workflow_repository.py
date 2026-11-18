"""Читання/запис SQLAlchemy. Авторизація — у сервісі."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.program import Program
from app.models.section import Section
from app.models.department import Department
from app.models.user import User
from app.models.measure import Measure, MeasureCollaborator
from app.models.program_workflow import ProgramDepartment, MeasureAssignment


class ProgramWorkflowRepository:
    def __init__(self, db: Session):
        self.db = db

    def program(self, program_id: str):
        return self.db.get(Program, program_id)

    def measure(self, measure_id: str):
        return self.db.get(Measure, measure_id)

    def department(self, department_id: str):
        return self.db.get(Department, department_id)

    def all_departments(self):
        return list(self.db.scalars(select(Department).order_by(Department.id)))

    def user(self, user_id: int):
        return self.db.get(User, user_id)

    def coordinators(self, department_id: str):
        return list(self.db.scalars(
            select(User).where(User.department_id == department_id, User.role_id == "KOORD")
            .order_by(User.id)
        ))

    def executors(self, department_id: str):
        return list(self.db.scalars(
            select(User).where(User.department_id == department_id, User.role_id == "VYK")
            .order_by(User.login)
        ))

    def dispatch(self, program_id: str, department_id: str):
        return self.db.get(ProgramDepartment, (program_id, department_id))

    def sent_programs(self, department_id: str):
        return list(self.db.scalars(
            select(Program)
            .join(ProgramDepartment, ProgramDepartment.program_id == Program.id)
            .where(ProgramDepartment.department_id == department_id)
            .order_by(Program.id)
        ))

    def owned_programs(self, user_id: int):
        return list(self.db.scalars(
            select(Program).where(Program.created_by_user_id == user_id).order_by(Program.id)
        ))

    def sections(self):
        return list(self.db.scalars(select(Section).order_by(Section.number, Section.id)))

    def all_programs(self):
        return list(self.db.scalars(select(Program).order_by(Program.id)))

    def all_measures(self, program_id: str):
        return list(self.db.scalars(
            select(Measure).where(Measure.program_id == program_id)
            .order_by(Measure.section_id, Measure.sequence_number, Measure.id)
        ))

    def measure_department_ids(self, measure: Measure) -> set[str]:
        """Відповідальний та всі співвиконавці."""
        result = {measure.responsible_department_id} if measure.responsible_department_id else set()
        result.update(self.db.scalars(
            select(MeasureCollaborator.department_id)
            .where(MeasureCollaborator.measure_id == measure.id)
        ))
        return result

    def measure_department_map(self, program_id: str, measures: list[Measure]):
        """Разова вибірка співвиконавців замість N+1 запитів."""
        result = {measure.id: {measure.responsible_department_id}
                  if measure.responsible_department_id else set() for measure in measures}
        for measure_id, department_id in self.db.execute(
            select(MeasureCollaborator.measure_id, MeasureCollaborator.department_id)
            .join(Measure, Measure.id == MeasureCollaborator.measure_id)
            .where(Measure.program_id == program_id)
        ):
            result[measure_id].add(department_id)
        return result

    def assigned_measures(self, user_id: int, department_id: str, program_id: str | None = None):
        """Лише персональні призначення. Право від направлення перевіряє сервіс."""
        stmt = (
            select(Measure).join(MeasureAssignment, MeasureAssignment.measure_id == Measure.id)
            .where(MeasureAssignment.user_id == user_id,
                   MeasureAssignment.department_id == department_id)
        )
        if program_id is not None:
            stmt = stmt.where(Measure.program_id == program_id)
        return list(self.db.scalars(stmt.order_by(Measure.id)))

    def assignment(self, measure_id: str, user_id: int):
        return self.db.get(MeasureAssignment, (measure_id, user_id))

    def assignments(self, measure_id: str):
        return list(self.db.scalars(
            select(MeasureAssignment).where(MeasureAssignment.measure_id == measure_id)
            .order_by(MeasureAssignment.department_id, MeasureAssignment.user_id)
        ))
