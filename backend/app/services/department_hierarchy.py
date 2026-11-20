"""Ієрархія підрозділів за parent_id, без висновків із префіксів ID.

Структура повинна бути деревом: відсутній батько або цикл спричиняють
DepartmentHierarchyError (викликаючий сервіс має відмовити в доступі).

Підтримує і ProgramWorkflowRepository, і DepartmentRepository через
мінімальний метод all_departments().
"""
from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Protocol, Sequence

if TYPE_CHECKING:
    from app.models.department import Department


class DepartmentSource(Protocol):
    def all_departments(self) -> Sequence[Department]: ...


class DepartmentHierarchyError(Exception):
    pass


class DepartmentHierarchy:
    def __init__(self, repository: DepartmentSource):
        departments = repository.all_departments()
        self.by_id = {dept.id: dept for dept in departments}
        self.parents = {dept.id: dept.parent_id for dept in departments}
        self.children: dict[str, set[str]] = defaultdict(set)

        for department_id, parent_id in self.parents.items():
            if parent_id is not None:
                if parent_id not in self.parents:
                    raise DepartmentHierarchyError(
                        f"Неіснуючий батьківський підрозділ {parent_id} для {department_id}"
                    )
                self.children[parent_id].add(department_id)

        for department_id in self.parents:
            visited: set[str] = set()
            current: str | None = department_id
            while current is not None:
                if current in visited:
                    raise DepartmentHierarchyError("В ієрархії підрозділів знайдено цикл")
                visited.add(current)
                current = self.parents[current]

    def exists(self, department_id: str) -> bool:
        return department_id in self.by_id

    def ancestors(self, department_id: str) -> set[str]:
        """Підрозділ та його батьківські підрозділи."""
        if not self.exists(department_id):
            return set()
        result: set[str] = set()
        current: str | None = department_id
        while current is not None:
            result.add(current)
            current = self.parents[current]
        return result

    def descendants(self, department_id: str) -> set[str]:
        """Підрозділ і всі його підпорядковані підрозділи."""
        if not self.exists(department_id):
            return set()
        result: set[str] = set()
        queue = [department_id]
        while queue:
            current = queue.pop()
            if current in result:
                continue
            result.add(current)
            queue.extend(self.children[current])
        return result

    def is_within(self, department_id: str, root_department_id: str) -> bool:
        return department_id in self.descendants(root_department_id)
