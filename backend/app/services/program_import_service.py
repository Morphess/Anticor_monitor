"""Атомарний імпорт програми із врахуванням власника та ієрархії підрозділів.

Створює Program, Section, Measure, MeasureCollaborator.
НЕ створює ProgramDepartment і MeasureAssignment — це окремий workflow.
"""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.measure import Measure, MeasureCollaborator
from app.models.program import Program
from app.models.section import Section
from app.repositories.program_import_repository import ProgramImportRepository
from app.schemas.program_import import ProgramImportPayload, ProgramImportResult
from app.services.department_hierarchy import DepartmentHierarchy, DepartmentHierarchyError


class ProgramImportConflict(Exception):
    """Об'єкт існує або порушено узгодженість довідників."""


class ProgramImportInvalidReference(Exception):
    """Недійсний зовнішній ключ або структура підпорядкування."""


class ProgramImportForbidden(Exception):
    """Спроба створити програму без повноважень."""


class ProgramImportService:
    def __init__(self, db: Session) -> None:
        self.repository = ProgramImportRepository(db)

    def import_program(self, payload: ProgramImportPayload, actor) -> ProgramImportResult:
        """Одна транзакція. Не змінює наявні програми, розсилки чи призначення."""
        repo = self.repository
        try:
            if actor.role_id not in {"ADMIN", "KOORD"}:
                raise ProgramImportForbidden("Імпортувати програму можуть лише ADMIN або KOORD")

            owner_user_id, coordinator_department_id = self._resolve_owner(payload, actor)
            self._validate_database_references(payload, coordinator_department_id)

            program_fields = payload.program.model_dump(
                exclude={"owner_coordinator_user_id", "coordinator_department_id"}
            )
            repo.add(Program(
                **program_fields,
                coordinator_department_id=coordinator_department_id,
                created_by_user_id=owner_user_id,
            ))
            # Розділи — глобальні, тому зіставляємо їх з існуючим довідником.
            sections_created = 0
            sections_reused = 0
            measures_created = 0
            collaborators_created = 0
            for section in payload.sections:
                if repo.section(section.id) is None:
                    repo.add(Section(id=section.id, number=section.number, title=section.title))
                    # Той самий ID може з'явитися в наступній ітерації, flush визначає FK-цілі.
                    sections_created += 1
                else:
                    sections_reused += 1

            repo.flush()
            for section in payload.sections:
                for item in section.measures:
                    measure_fields = item.model_dump(
                        exclude={"assigned_user_id", "collaborator_department_ids"}
                    )
                    repo.add(Measure(
                        **measure_fields,
                        program_id=payload.program.id,
                        section_id=section.id,
                        assigned_user_id=None,  # тільки через workflow.measures/{id}/assign
                    ))
                    measures_created += 1
                    for dep_id in item.collaborator_department_ids:
                        repo.add(MeasureCollaborator(measure_id=item.id, department_id=dep_id))
                        collaborators_created += 1

            repo.commit()  # лише тут виникає стійкий запис у PostgreSQL
            return ProgramImportResult(
                program_id=payload.program.id,
                created_by_user_id=owner_user_id,
                coordinator_department_id=coordinator_department_id,
                sections_created=sections_created,
                sections_reused=sections_reused,
                measures_created=measures_created,
                collaborators_created=collaborators_created,
            )
        except IntegrityError as exc:
            repo.rollback()
            raise ProgramImportConflict(
                "База відхилила імпорт через порушення унікальності або зовнішнього ключа"
            ) from exc
        except Exception:
            repo.rollback()
            raise

    def _resolve_owner(self, payload: ProgramImportPayload, actor) -> tuple[int | None, str | None]:
        """KOORD завжди є власником своєї програми; ADMIN може обрати KOORD-власника."""
        program_data = payload.program
        repo = self.repository

        if actor.role_id == "KOORD":
            if actor.department_id is None:
                raise ProgramImportInvalidReference("Координатор повинен належати до підрозділу")
            if (program_data.owner_coordinator_user_id is not None
                    and program_data.owner_coordinator_user_id != actor.id):
                raise ProgramImportForbidden("KOORD не може призначати іншого головного координатора")
            if (program_data.coordinator_department_id is not None
                    and program_data.coordinator_department_id != actor.department_id):
                raise ProgramImportForbidden("KOORD може створити програму лише для власного підрозділу")
            return actor.id, actor.department_id

        # ADMIN може імпортувати від імені існуючого KOORD або без призначення власника.
        owner_user_id = program_data.owner_coordinator_user_id
        if owner_user_id is not None:
            owner = repo.user(owner_user_id)
            if owner is None or owner.role_id != "KOORD" or owner.department_id is None:
                raise ProgramImportInvalidReference(
                    "owner_coordinator_user_id має вказувати на існуючого KOORD із підрозділом"
                )
            if (program_data.coordinator_department_id is not None
                    and program_data.coordinator_department_id != owner.department_id):
                raise ProgramImportInvalidReference(
                    "coordinator_department_id має збігатися з підрозділом KOORD-власника"
                )
            return owner.id, owner.department_id

        return None, program_data.coordinator_department_id

    def _validate_database_references(
        self, payload: ProgramImportPayload, coordinator_department_id: str | None
    ) -> None:
        repo = self.repository
        if repo.program(payload.program.id) is not None:
            raise ProgramImportConflict(f"Програма '{payload.program.id}' уже існує")

        for section in payload.sections:
            existing = repo.section(section.id)
            if existing is not None and (
                existing.number != section.number or existing.title != section.title
            ):
                raise ProgramImportConflict(
                    f"Розділ '{section.id}' існує з іншим номером або назвою"
                )
            same_number = repo.section_with_number(section.number)
            if same_number is not None and same_number.id != section.id:
                raise ProgramImportConflict(
                    f"Номер розділу {section.number} уже належить '{same_number.id}'"
                )
            for item in section.measures:
                if repo.measure(item.id) is not None:
                    raise ProgramImportConflict(f"Захід '{item.id}' уже існує")

        # Ієрархія має бути дійсною ще до імпорту; маршрутизація не повинна впасти після POST.
        try:
            DepartmentHierarchy(repo)
        except DepartmentHierarchyError as exc:
            raise ProgramImportInvalidReference(f"Некоректна ієрархія підрозділів: {exc}") from exc

        departments: set[str] = set()
        risks: set[str] = set()
        if coordinator_department_id:
            departments.add(coordinator_department_id)
        for section in payload.sections:
            for item in section.measures:
                departments.add(item.responsible_department_id)
                departments.update(item.collaborator_department_ids)
                if item.risk_id:
                    risks.add(item.risk_id)

        missing_departments = sorted(d for d in departments if repo.department(d) is None)
        missing_risks = sorted(r for r in risks if repo.risk(r) is None)
        errors: list[str] = []
        if missing_departments:
            errors.append("підрозділи: " + ", ".join(missing_departments))
        if missing_risks:
            errors.append("ризики: " + ", ".join(missing_risks))
        if errors:
            raise ProgramImportInvalidReference("Відсутні записи в БД — " + "; ".join(errors))
