"""Підпорядкованість підрозділів: перевірка вищого підрозділу без бази даних."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
os.environ.setdefault("JWT_SECRET_KEY", "synthetic-test-key-for-hs256-at-least-32-bytes")
os.environ.setdefault("APP_NAME", "BorderGroup Test")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("SQL_ECHO", "false")

from app.schemas.departments import DepartmentCreate, DepartmentRead, DepartmentUpdate
from app.services.department_services import DepartmentService


def service_with(tree):
    """tree: {id: parent_id} — вигадана ієрархія P01 → OU → OU-HR."""
    service = DepartmentService(Mock())
    service.repository = Mock()
    service.repository.get_by_id.side_effect = lambda dep_id: (
        SimpleNamespace(id=dep_id, parent_id=tree[dep_id]) if dep_id in tree else None
    )
    service.repository.all_departments.return_value = [SimpleNamespace(id=k, parent_id=v) for k,v in tree.items()]
    return service


class DepartmentParentTests(unittest.TestCase):
    def setUp(self):
        self.service = service_with({"P01": None, "OU": "P01", "OU-HR": "OU"})

    def test_top_level_is_allowed(self):
        self.assertIsNone(self.service._validated_parent(None, department_id="NEW", hierarchy=self.service._hierarchy()))

    def test_existing_parent_is_accepted(self):
        self.assertEqual(self.service._validated_parent("OU", department_id="NEW", hierarchy=self.service._hierarchy()), "OU")

    def test_unknown_parent_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            self.service._validated_parent("NOPE", department_id="NEW", hierarchy=self.service._hierarchy())
        self.assertEqual(ctx.exception.status_code, 422)

    def test_self_parent_is_rejected(self):
        with self.assertRaises(HTTPException):
            self.service._validated_parent("OU", department_id="OU", hierarchy=self.service._hierarchy())

    def test_cycle_through_descendant_is_rejected(self):
        # P01 не може стати підлеглим свого ж нащадка OU-HR.
        with self.assertRaises(HTTPException) as ctx:
            self.service._validated_parent("OU-HR", department_id="P01", hierarchy=self.service._hierarchy())
        self.assertIn("цикл", ctx.exception.detail)

    def test_schemas_carry_parent(self):
        self.assertEqual(DepartmentCreate(id="X", name="Н", department_type="Т", parent_id="P01").parent_id, "P01")
        self.assertIn("parent_id", DepartmentUpdate(parent_id=None).model_dump(exclude_unset=True))
        read = DepartmentRead.model_validate(SimpleNamespace(id="X", name="Н", department_type="Т", notes="", parent_id="P01"))
        self.assertEqual(read.parent_id, "P01")


if __name__ == "__main__":
    unittest.main()
