"""CRUD підрозділів з валідацією parent_id і захистом структури доступів."""
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.department import Department
from app.repositories.department_repository import DepartmentRepository
from app.schemas.departments import DepartmentCreate, DepartmentTreeRead, DepartmentUpdate
from app.services.department_hierarchy import DepartmentHierarchy, DepartmentHierarchyError


class DepartmentService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = DepartmentRepository(db)

    def _get_or_404(self, department_id: str) -> Department:
        department = self.repository.get_by_id(department_id)
        if department is None:
            raise HTTPException(status_code=404, detail="Підрозділ не знайдено")
        return department

    @staticmethod
    def _required_text(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Поле '{field}' не може бути порожнім",
            )
        return cleaned

<<<<<<< HEAD
    def _hierarchy(self) -> DepartmentHierarchy:
        try:
            return DepartmentHierarchy(self.repository)
        except DepartmentHierarchyError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Некоректна ієрархія підрозділів: {exc}",
            ) from exc

    def _validated_parent(
        self, parent_id: str | None, *, department_id: str, hierarchy: DepartmentHierarchy
    ) -> str | None:
=======
    def _check_parent(self, department_id: str, parent_id: str | None) -> str | None:
        """Вищий підрозділ має існувати й не може бути самим підрозділом чи його нащадком."""
>>>>>>> f5ebfe2abbde2cbf98b13f619b74ebb1fa49b2c7
        if parent_id is None:
            return None
        parent_id = self._required_text(parent_id, "parent_id")
        if parent_id == department_id:
<<<<<<< HEAD
            raise HTTPException(status_code=409, detail="Підрозділ не може бути власним батьком")
        if not hierarchy.exists(parent_id):
            raise HTTPException(status_code=422, detail=f"Батьківський підрозділ '{parent_id}' не існує")
        # Під час редагування забороняємо перенесення підрозділу всередину своєї гілки.
        if department_id in hierarchy.by_id and parent_id in hierarchy.descendants(department_id):
            raise HTTPException(status_code=409, detail="Зміна parent_id створює цикл підпорядкування")
=======
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Підрозділ не може підпорядковуватися сам собі",
            )
        current = self.repository.get_by_id(parent_id)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Вищий підрозділ не знайдено",
            )
        seen = set()
        while current is not None and current.id not in seen:
            if current.id == department_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Не можна підпорядкувати підрозділ його ж підлеглому",
                )
            seen.add(current.id)
            current = self.repository.get_by_id(current.parent_id) if current.parent_id else None
>>>>>>> f5ebfe2abbde2cbf98b13f619b74ebb1fa49b2c7
        return parent_id

    def get_all(self) -> list[Department]:
        return self.repository.get_all()

    def get_by_id(self, department_id: str) -> Department:
        return self._get_or_404(department_id)

    def get_tree(self) -> list[DepartmentTreeRead]:
        hierarchy = self._hierarchy()

        def node(department_id: str) -> DepartmentTreeRead:
            department = hierarchy.by_id[department_id]
            return DepartmentTreeRead(
                id=department.id,
                name=department.name,
                department_type=department.department_type,
                notes=department.notes,
                parent_id=department.parent_id,
                children=[node(child) for child in sorted(hierarchy.children[department_id])],
            )

        roots = sorted(id_ for id_, parent in hierarchy.parents.items() if parent is None)
        return [node(root_id) for root_id in roots]

    def create(self, data: DepartmentCreate) -> Department:
        department_id = self._required_text(data.id, "id")
        name = self._required_text(data.name, "name")
        department_type = self._required_text(data.department_type, "department_type")
        hierarchy = self._hierarchy()

        if self.repository.get_by_id(department_id) is not None:
            raise HTTPException(status_code=409, detail="Підрозділ із таким кодом уже існує")

<<<<<<< HEAD
        parent_id = self._validated_parent(
            data.parent_id, department_id=department_id, hierarchy=hierarchy
        )
=======
        parent_id = self._check_parent(department_id, data.parent_id)

>>>>>>> f5ebfe2abbde2cbf98b13f619b74ebb1fa49b2c7
        department = Department(
            id=department_id,
            name=name,
            department_type=department_type,
            notes=data.notes,
            parent_id=parent_id,
        )
        try:
            self.repository.add(department)
            self.db.commit()
            self.db.refresh(department)
            return department
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Операцію заблоковано обмеженнями БД") from exc
        except Exception:
            self.db.rollback()
            raise

    def update(self, department_id: str, data: DepartmentUpdate) -> Department:
        department = self._get_or_404(department_id)
        changes = data.model_dump(exclude_unset=True)

<<<<<<< HEAD
        # Повністю перевіряємо зміну ієрархії ДО зміни ORM-об'єкта.
        if "parent_id" in changes:
            changes["parent_id"] = self._validated_parent(
                changes["parent_id"],
                department_id=department_id,
                hierarchy=self._hierarchy(),
            )
=======
        if "parent_id" in changes:
            department.parent_id = self._check_parent(department_id, changes.pop("parent_id"))
>>>>>>> f5ebfe2abbde2cbf98b13f619b74ebb1fa49b2c7

        for field, value in changes.items():
            if field == "parent_id":
                continue  # null для parent_id допустимий: від'єднати від батька.
            if value is None:
                raise HTTPException(status_code=422, detail=f"Поле '{field}' не може бути null")
            if field in {"name", "department_type"}:
                changes[field] = self._required_text(value, field)

        for field, value in changes.items():
            setattr(department, field, value)

        try:
            self.repository.save()
            self.db.commit()
            self.db.refresh(department)
            return department
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Операцію заблоковано обмеженнями БД") from exc
        except Exception:
            self.db.rollback()
            raise

    def delete(self, department_id: str) -> None:
        department = self._get_or_404(department_id)
        if self.repository.has_children(department_id):
            raise HTTPException(
                status_code=409,
                detail="Спочатку перенесіть або видаліть підпорядковані підрозділи",
            )
        try:
            self.repository.delete(department)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail="Підрозділ використовується в інших записах") from exc
        except Exception:
            self.db.rollback()
            raise
