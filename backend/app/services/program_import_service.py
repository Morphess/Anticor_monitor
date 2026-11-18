"""Імпорт JSON у PostgreSQL однією транзакцією."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.measure import Measure, MeasureCollaborator
from app.models.program import Program
from app.models.section import Section
from app.repositories.program_import_repository import ProgramImportRepository
from app.schemas.program_import import ProgramImportPayload, ProgramImportResult


class ProgramImportConflict(Exception):
    """Програма/розділ/захід уже є або конфліктує з даними БД."""


class ProgramImportInvalidReference(Exception):
    """У JSON вказано ID зовнішнього об'єкта, якого немає у БД."""


class ProgramImportService:
    def __init__(self, db: Session) -> None:
        self.repository = ProgramImportRepository(db)

    def import_program(self, payload: ProgramImportPayload) -> ProgramImportResult:
        """Імпортує програму, спільні розділи та заходи, або відкочує все.

        Повторний імпорт тієї самої програми — 409, без перезаписування.
        Довідники підрозділів, ризиків і користувачів не створюються.
        """
        repo = self.repository
        try:
            self._validate_database_references(payload)

            repo.add(Program(**payload.program.model_dump()))
            created_sections = 0
            reused_sections = 0
            created_measures = 0
            created_collaborators = 0

            for section in payload.sections:
                existing_section = repo.section(section.id)
                if existing_section is None:
                    repo.add(Section(id=section.id, number=section.number, title=section.title))
                    created_sections += 1
                else:
                    reused_sections += 1

                for item in section.measures:
                    fields = item.model_dump(exclude={"collaborator_department_ids"})
                    repo.add(
                        Measure(
                            program_id=payload.program.id,
                            section_id=section.id,
                            **fields,
                        )
                    )
                    created_measures += 1
                    for department_id in item.collaborator_department_ids:
                        repo.add(
                            MeasureCollaborator(
                                measure_id=item.id,
                                department_id=department_id,
                            )
                        )
                        created_collaborators += 1

            repo.commit()  # ОДНА транзакція для всіх записів
            return ProgramImportResult(
                program_id=payload.program.id,
                sections_created=created_sections,
                sections_reused=reused_sections,
                measures_created=created_measures,
                collaborators_created=created_collaborators,
            )
        except IntegrityError as exc:
            repo.rollback()
            raise ProgramImportConflict(
                "База даних відхилила імпорт: порушено унікальність або зовнішній ключ"
            ) from exc
        except Exception:
            repo.rollback()
            raise

    def _validate_database_references(self, payload: ProgramImportPayload) -> None:
        repo = self.repository
        program_id = payload.program.id
        if repo.program(program_id) is not None:
            raise ProgramImportConflict(f"Програма '{program_id}' уже існує")

        # sections — ГЛОБАЛЬНИЙ довідник, а не підтаблиця programs.
        for section in payload.sections:
            existing = repo.section(section.id)
            if existing is not None and (
                existing.number != section.number or existing.title != section.title
            ):
                raise ProgramImportConflict(
                    f"Розділ '{section.id}' існує з іншими номером або назвою"
                )
            same_number = repo.section_with_number(section.number)
            if same_number is not None and same_number.id != section.id:
                raise ProgramImportConflict(
                    f"Номер розділу {section.number} уже використовує '{same_number.id}'"
                )
            for item in section.measures:
                if repo.measure(item.id) is not None:
                    raise ProgramImportConflict(f"Захід '{item.id}' уже існує")

        department_ids: set[str] = set()
        risk_ids: set[str] = set()
        user_ids: set[int] = set()
        if payload.program.coordinator_department_id is not None:
            department_ids.add(payload.program.coordinator_department_id)
        for section in payload.sections:
            for item in section.measures:
                if item.responsible_department_id is not None:
                    department_ids.add(item.responsible_department_id)
                department_ids.update(item.collaborator_department_ids)
                if item.risk_id is not None:
                    risk_ids.add(item.risk_id)
                if item.assigned_user_id is not None:
                    user_ids.add(item.assigned_user_id)

        missing_departments = sorted(x for x in department_ids if repo.department(x) is None)
        missing_risks = sorted(x for x in risk_ids if repo.risk(x) is None)
        missing_users = sorted(x for x in user_ids if repo.user(x) is None)
        errors = []
        if missing_departments:
            errors.append("підрозділи: " + ", ".join(missing_departments))
        if missing_risks:
            errors.append("ризики: " + ", ".join(missing_risks))
        if missing_users:
            errors.append("користувачі: " + ", ".join(map(str, missing_users)))
        if errors:
            raise ProgramImportInvalidReference("Відсутні записи в БД — " + "; ".join(errors))
