"""Головний KOORD -> підрозділ -> підлеглі підрозділи -> особисті призначення."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.program_workflow import ProgramDepartment, MeasureAssignment
from app.repositories.program_workflow_repository import ProgramWorkflowRepository
from app.services.department_hierarchy import (
    DepartmentHierarchy,
    DepartmentHierarchyError,
)


class WorkflowError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def deny(detail: str = "Недостатньо прав"):
    raise WorkflowError(403, detail)


class ProgramWorkflowService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProgramWorkflowRepository(db)
        self._tree = None

    @property
    def tree(self) -> DepartmentHierarchy:
        if self._tree is None:
            try:
                self._tree = DepartmentHierarchy(self.repo)
            except DepartmentHierarchyError as exc:
                raise WorkflowError(409, str(exc)) from exc
        return self._tree

    def _program(self, program_id: str):
        program = self.repo.program(program_id)
        if program is None:
            raise WorkflowError(404, "Програму не знайдено")
        return program

    def _measure(self, measure_id: str):
        measure = self.repo.measure(measure_id)
        if measure is None:
            raise WorkflowError(404, "Захід не знайдено")
        return measure

    @staticmethod
    def _owner(user, program) -> bool:
        return user.role_id == "KOORD" and program.created_by_user_id == user.id

    def _direct_recipient(self, actor, program_id: str) -> bool:
        return (
            actor.role_id == "KOORD"
            and actor.department_id is not None
            and self.repo.dispatch(program_id, actor.department_id) is not None
        )

    def _is_delivered_to(self, program_id: str, department_id: str) -> bool:
        """Направлення до батьківського підрозділу покриває його нащадків."""
        return any(
            self.repo.dispatch(program_id, ancestor_id) is not None
            for ancestor_id in self.tree.ancestors(department_id)
        )

    def _can_manage_target(self, actor, program_id: str, target_department_id: str):
        if not self.tree.exists(target_department_id):
            raise WorkflowError(404, "Підрозділ не знайдено")
        if actor.role_id == "ADMIN":
            if not self._is_delivered_to(program_id, target_department_id):
                deny("Програму не направлено до цієї гілки підрозділів")
            return
        if not self._direct_recipient(actor, program_id):
            deny("Координатор не отримав цю програму у своєму підрозділі")
        if not self.tree.is_within(target_department_id, actor.department_id):
            deny("Можна обирати лише свій та підпорядковані підрозділи")

    def _measure_allows_target(self, measure, target_department_id: str) -> bool:
        """Захід відповідального/співвиконавця може передаватися НИЖЧЕ його підрозділу.

        Приклад: відповідальний P01 => можна призначити P01-A, але не P02-A;
        відповідальний P01-A => не можна призначити P01-B (сусідня гілка).
        """
        allowed_sources = self.repo.measure_department_ids(measure)
        return bool(allowed_sources & self.tree.ancestors(target_department_id))

    def _visible_to_coordinator(
        self, measure, actor_department: str, source_departments: set[str]
    ) -> bool:
        """Координатор бачить заходи своєї гілки та батьківського рівня."""
        my_ancestors = self.tree.ancestors(actor_department)
        my_descendants = self.tree.descendants(actor_department)
        return bool(source_departments & (my_ancestors | my_descendants))

    def _accessible_assigned_measures(self, actor, program_id: str | None = None):
        if actor.role_id != "VYK" or not actor.department_id:
            return []
        if not self.tree.exists(actor.department_id):
            return []
        return [
            measure
            for measure in self.repo.assigned_measures(
                actor.id, actor.department_id, program_id
            )
            if (
                self._is_delivered_to(measure.program_id, actor.department_id)
                and self._measure_allows_target(measure, actor.department_id)
            )
        ]

    def available_departments(self, program_id: str, actor):
        """Для селектора підрозділів у кабінеті. Сервер не довіряє цьому списку при POST."""
        program = self._program(program_id)
        if actor.role_id == "ADMIN" or self._owner(actor, program):
            departments = list(self.tree.by_id.values())
        elif self._direct_recipient(actor, program_id):
            departments = [
                self.tree.by_id[dep_id]
                for dep_id in self.tree.descendants(actor.department_id)
            ]
        else:
            deny("Немає доступу до вибору підрозділів цієї програми")
        return [
            {"id": dept.id, "name": dept.name, "parent_id": dept.parent_id}
            for dept in sorted(departments, key=lambda d: d.id)
        ]

    def send_to_departments(self, program_id: str, department_ids: list[str], actor):
        program = self._program(program_id)
        is_central = actor.role_id == "ADMIN" or self._owner(actor, program)
        if not is_central and not self._direct_recipient(actor, program_id):
            deny(
                "Направляти програму може її головний координатор або координатор-одержувач"
            )
        unique_ids = list(dict.fromkeys(department_ids))
        if not unique_ids or any(not dep or dep != dep.strip() for dep in unique_ids):
            raise WorkflowError(422, "Передай непорожні коректні коди підрозділів")

        results = []
        # УСІ перевірки робляться до першого запису (атомарність).
        for target in unique_ids:
            if not self.tree.exists(target):
                raise WorkflowError(422, f"Невідомий підрозділ: {target}")
            if not is_central:
                if target == actor.department_id or not self.tree.is_within(
                    target, actor.department_id
                ):
                    deny(
                        "Координатор може перенаправляти програму лише в підлеглі підрозділи"
                    )
            coordinators = self.repo.coordinators(target)
            if not coordinators:
                raise WorkflowError(
                    409, f"У підрозділі {target} немає користувача з роллю KOORD"
                )
            old = self.repo.dispatch(program_id, target)
            results.append(
                {
                    "department_id": target,
                    "coordinators": coordinators,
                    "already_sent": old is not None,
                    "existing": old,
                }
            )
        try:
            for row in results:
                if row["existing"] is None:
                    self.db.add(
                        ProgramDepartment(
                            program_id=program_id,
                            department_id=row["department_id"],
                            sent_by_user_id=actor.id,
                        )
                    )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        for row in results:
            row.pop("existing")
        return {"program_id": program_id, "departments": results}

    def my_programs(self, actor):
        by_id = {}
        if actor.role_id == "ADMIN":
            for program in self.repo.all_programs():
                by_id[program.id] = {
                    "id": program.id,
                    "title": program.title,
                    "access_type": "admin",
                }
        elif actor.role_id == "KOORD":
            for program in self.repo.owned_programs(actor.id):
                by_id[program.id] = {
                    "id": program.id,
                    "title": program.title,
                    "access_type": "owner",
                }
            if actor.department_id:
                for program in self.repo.sent_programs(actor.department_id):
                    by_id.setdefault(
                        program.id,
                        {
                            "id": program.id,
                            "title": program.title,
                            "access_type": "department_coordinator",
                        },
                    )
        elif actor.role_id == "VYK" and actor.department_id:
            for measure in self._accessible_assigned_measures(actor):
                if measure.program_id not in by_id:
                    program = self.repo.program(measure.program_id)
                    by_id[program.id] = {
                        "id": program.id,
                        "title": program.title,
                        "access_type": "executor",
                    }
        return sorted(by_id.values(), key=lambda row: row["id"])

    def visible_program(self, program_id: str, actor):
        program = self._program(program_id)
        if not any(row["id"] == program_id for row in self.my_programs(actor)):
            deny("Немає доступу до програми")
        return program

    def program_sections(self, program_id: str, actor):
        # Отримуємо лише доступні користувачу заходи програми
        visible_measures = self.program_measures(program_id, actor)

        # Збираємо ID розділів цих заходів
        section_ids = {m["section_id"] for m in visible_measures}

        # Повертаємо лише відповідні розділи
        return [
            {
                "id": sec.id,
                "number": sec.number,
                "title": sec.title,
            }
            for sec in self.repo.sections()
            if sec.id in section_ids
        ]

    def program_measures(self, program_id: str, actor):
        program = self._program(program_id)
        if actor.role_id == "ADMIN" or self._owner(actor, program):
            measures = self.repo.all_measures(program_id)
        elif self._direct_recipient(actor, program_id):
            all_measures = self.repo.all_measures(program_id)
            sources = self.repo.measure_department_map(program_id, all_measures)
            measures = [
                m
                for m in all_measures
                if self._visible_to_coordinator(m, actor.department_id, sources[m.id])
            ]
        elif actor.role_id == "VYK" and actor.department_id:
            measures = self._accessible_assigned_measures(actor, program_id)
            if not measures:
                deny("Тобі не призначено заходів цієї програми")
        else:
            deny("Немає доступу до програми")
        return [self._brief(measure) for measure in measures]

    @staticmethod
    def _brief(measure):
        return {
            "id": measure.id,
            "program_id": measure.program_id,
            "section_id": measure.section_id,
            "description": measure.description,
            "responsible_department_id": measure.responsible_department_id,
        }

    def my_measures(self, actor):
        if actor.role_id != "VYK" or not actor.department_id:
            deny("Цей перелік призначений лише для виконавців із підрозділом")
        return [self._brief(m) for m in self._accessible_assigned_measures(actor)]

    def department_coordinators(self, program_id: str, department_id: str, actor):
        program = self._program(program_id)
        if not (actor.role_id == "ADMIN" or self._owner(actor, program)):
            self._can_manage_target(actor, program_id, department_id)
        if not self.tree.exists(department_id):
            raise WorkflowError(404, "Підрозділ не знайдено")
        return self.repo.coordinators(department_id)

    def department_executors(self, program_id: str, department_id: str, actor):
        self._program(program_id)
        self._can_manage_target(actor, program_id, department_id)
        return self.repo.executors(department_id)

    def assign(self, measure_id: str, department_id: str, user_id: int, actor):
        measure = self._measure(measure_id)
        self._can_manage_target(actor, measure.program_id, department_id)
        if not self._measure_allows_target(measure, department_id):
            raise WorkflowError(409, "Захід не стосується цієї гілки підрозділів")
        target = self.repo.user(user_id)
        if target is None:
            raise WorkflowError(404, "Користувача не знайдено")
        if target.department_id != department_id or target.role_id != "VYK":
            raise WorkflowError(422, "Користувач має бути VYK обраного підрозділу")
        old = self.repo.assignment(measure_id, user_id)
        if old is not None:
            return {"assignment": old, "already_assigned": True}
        record = MeasureAssignment(
            measure_id=measure_id,
            user_id=user_id,
            department_id=department_id,
            assigned_by_user_id=actor.id,
        )
        try:
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
        except Exception:
            self.db.rollback()
            raise
        return {"assignment": record, "already_assigned": False}

    def list_assignments(self, measure_id: str, actor):
        measure = self._measure(measure_id)
        program = self._program(measure.program_id)
        if actor.role_id == "ADMIN" or self._owner(actor, program):
            return self.repo.assignments(measure_id)
        if not self._direct_recipient(actor, measure.program_id):
            deny()
        if not self._visible_to_coordinator(
            measure, actor.department_id, self.repo.measure_department_ids(measure)
        ):
            deny("Захід не стосується гілки координатора")
        return [
            row
            for row in self.repo.assignments(measure_id)
            if self.tree.is_within(row.department_id, actor.department_id)
        ]

    def revoke(self, measure_id: str, user_id: int, actor):
        measure = self._measure(measure_id)
        record = self.repo.assignment(measure_id, user_id)
        if record is None:
            raise WorkflowError(404, "Призначення не знайдено")
        self._can_manage_target(actor, measure.program_id, record.department_id)
        try:
            self.db.delete(record)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
