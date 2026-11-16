from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth_user import AuthUser


class SqlAlchemyAuthRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_password_hash(self, login: str) -> str | None:
        statement = select(AuthUser.password_hash).where(AuthUser.login == login)
        return self.db.scalar(statement)
