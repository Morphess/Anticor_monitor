"""Пошук і сторінки журналу дій для кабінету адміністратора."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.action_log import ActionLog
from app.models.department import Department
from app.models.user import User


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ActionLogFeedRepository:
    def __init__(self, db: Session):
        self.db = db

    def _filtered(self, *, q, actor_user_id, department_id, action, entity_type, since, until):
        stmt = (
            select(ActionLog, User, Department)
            .outerjoin(User, User.id == ActionLog.actor_user_id)
            .outerjoin(Department, Department.id == User.department_id)
        )
        if actor_user_id is not None:
            stmt = stmt.where(ActionLog.actor_user_id == actor_user_id)
        if department_id == "-":
            # Дії без підрозділу: системні або користувачів без підрозділу.
            stmt = stmt.where(User.department_id.is_(None))
        elif department_id:
            stmt = stmt.where(User.department_id == department_id)
        if action:
            stmt = stmt.where(ActionLog.action == action)
        if entity_type:
            stmt = stmt.where(ActionLog.entity_type == entity_type)
        if since is not None:
            stmt = stmt.where(ActionLog.occurred_at >= since)
        if until is not None:
            stmt = stmt.where(ActionLog.occurred_at <= until)
        for word in (q or "").split():
            pattern = f"%{_escape_like(word)}%"
            stmt = stmt.where(or_(
                ActionLog.entity_type.ilike(pattern, escape="\\"),
                ActionLog.entity_id.ilike(pattern, escape="\\"),
                ActionLog.field_name.ilike(pattern, escape="\\"),
                ActionLog.old_value.ilike(pattern, escape="\\"),
                ActionLog.new_value.ilike(pattern, escape="\\"),
                ActionLog.action.ilike(pattern, escape="\\"),
                User.login.ilike(pattern, escape="\\"),
                User.position.ilike(pattern, escape="\\"),
                Department.name.ilike(pattern, escape="\\"),
                cast(ActionLog.actor_user_id, String).ilike(pattern, escape="\\"),
            ))
        return stmt

    def page(self, *, page: int, page_size: int, q: str | None = None,
             actor_user_id: int | None = None, department_id: str | None = None,
             action: str | None = None, entity_type: str | None = None,
             since: datetime | None = None, until: datetime | None = None):
        stmt = self._filtered(q=q, actor_user_id=actor_user_id, department_id=department_id,
                              action=action, entity_type=entity_type, since=since, until=until)
        total = self.db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
        rows = self.db.execute(
            stmt.order_by(ActionLog.occurred_at.desc(), ActionLog.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        return total, rows

    def facets(self) -> tuple[list[str], list[str]]:
        actions = list(self.db.scalars(select(ActionLog.action).distinct().order_by(ActionLog.action)))
        entities = list(self.db.scalars(select(ActionLog.entity_type).distinct().order_by(ActionLog.entity_type)))
        return actions, entities
