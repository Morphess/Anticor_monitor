from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.section import Section
from app.repositories.section_repository import (
    SectionRepository,
)
from app.schemas.section import (
    SectionCreate,
    SectionUpdate,
)


class SectionNotFoundError(Exception):
    pass


class SectionAlreadyExistsError(Exception):
    pass


class InvalidSectionDataError(Exception):
    pass


class SectionService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = SectionRepository(db)

    # СПИСОК РОЗДІЛІВ
    def list_sections(self) -> list[Section]:
        return self.repo.get_all()

    # ОТРИМАТИ ОДИН РОЗДІЛ
    def get_section(self, section_id: str) -> Section:
        section = self.repo.get_by_id(section_id)

        if section is None:
            raise SectionNotFoundError(f"Розділ '{section_id}' не знайдено")

        return section

    # СТВОРЕННЯ ВІДСУТНЬОГО РОЗДІЛУ
    def create_section(
        self,
        data: SectionCreate,
    ) -> Section:

        if self.repo.get_by_id(data.id) is not None:
            raise SectionAlreadyExistsError(f"Розділ '{data.id}' уже існує")

        if self.repo.get_by_number(data.number) is not None:
            raise SectionAlreadyExistsError(f"Розділ №{data.number} уже існує")

        section = Section(
            id=data.id,
            number=data.number,
            title=data.title.strip(),
        )

        if not section.title:
            raise InvalidSectionDataError("Назва розділу не може бути порожньою")

        try:
            self.repo.add(section)
            self.db.commit()
            self.db.refresh(section)
            return section

        except IntegrityError as error:
            self.db.rollback()
            raise SectionAlreadyExistsError(
                "Конфлікт коду або номера розділу"
            ) from error

        except Exception:
            self.db.rollback()
            raise

    # РЕДАГУВАННЯ НАЗВИ РОЗДІЛУ
    def update_section(
        self,
        section_id: str,
        data: SectionUpdate,
    ) -> Section:

        section = self.get_section(section_id)

        title = data.title.strip()

        if not title:
            raise InvalidSectionDataError("Назва розділу не може бути порожньою")

        section.title = title

        try:
            self.repo.save(section)
            self.db.commit()
            self.db.refresh(section)
            return section

        except IntegrityError as error:
            self.db.rollback()
            raise InvalidSectionDataError("Не вдалося оновити розділ") from error

        except Exception:
            self.db.rollback()
            raise
