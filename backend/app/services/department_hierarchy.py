"""Ієрархія підрозділів. Жодних прав за префіксами ID — тільки parent_id з БД.

Цикл, відсутній батько або зламані зв'язки => 409 (fail closed).
"""
from collections import defaultdict

from app.repositories.program_workflow_repository import ProgramWorkflowRepository


class DepartmentHierarchyError(Exception):
    pass


class DepartmentHierarchy:
    def __init__(self, repository: ProgramWorkflowRepository):
        departments = repository.all_departments()
        self.by_id = {dept.id: dept for dept in departments}
        self.parents = {dept.id: dept.parent_id for dept in departments}
        self.children = defaultdict(set)
        for department_id, parent_id in self.parents.items():
            if parent_id is not None:
                if parent_id not in self.parents:
                    raise DepartmentHierarchyError(
                        f"Неіснуючий батьківський підрозділ {parent_id} для {department_id}"
                    )
                self.children[parent_id].add(department_id)

        # Ніколи не трактуємо цикли як законне підпорядкування.
        for department_id in self.parents:
            visited = set()
            current = department_id
            while current is not None:
                if current in visited:
                    raise DepartmentHierarchyError("В ієрархії підрозділів знайдено цикл")
                visited.add(current)
                current = self.parents[current]

    def exists(self, department_id: str) -> bool:
        return department_id in self.by_id

    def ancestors(self, department_id: str) -> set[str]:
        """Підрозділ + усі його предки."""
        if not self.exists(department_id):
            return set()
        result = set()
        current = department_id
        while current is not None:
            result.add(current)
            current = self.parents[current]
        return result

    def descendants(self, department_id: str) -> set[str]:
        """Підрозділ + усі рівні нащадків."""
        if not self.exists(department_id):
            return set()
        result, queue = set(), [department_id]
        while queue:
            current = queue.pop()
            if current in result:
                continue
            result.add(current)
            queue.extend(self.children[current])
        return result

    def is_within(self, department_id: str, root_department_id: str) -> bool:
        """target department_id належить піддереву root (включно з root)."""
        return department_id in self.descendants(root_department_id)
