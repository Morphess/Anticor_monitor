from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:

    def __init__(self, db: Session):
        # Поточна сесія PostgreSQL
        self.db = db

    # Знайти користувача за ID
    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    # Знайти користувача за логіном
    def get_by_login(self, login: str) -> User | None:
        stmt = select(User).where(User.login == login)
        return self.db.scalar(stmt)

    # Отримати список користувачів
    def list_users(self, skip: int = 0, limit: int = 20) -> list[User]:

        stmt = select(User).order_by(User.id).offset(skip).limit(limit)

        return list(self.db.scalars(stmt).all())

    # Створити користувача
    def add(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    # Зберегти зміни користувача
    def save(self, user: User) -> User:
        self.db.commit()
        self.db.refresh(user)
        return user

    # Призначити користувачу антикорупційну програму
    def assign_program(
        self,
        user: User,
        program_id: str | None,
    ) -> User:

        user.program_id = program_id

        self.db.commit()
        self.db.refresh(user)

        return user

    # Видалити користувача
    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.commit()
