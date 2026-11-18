from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password

from app.models.user import User
from app.models.role import Role
from app.models.program import Program
from app.models.department import Department

from app.repositories.user_repository import UserRepository
from app.schemas.users import UserCreate, UserUpdate


# Власні типи помилок
class UserNotFoundError(Exception):
    pass


class UserAlreadyExistsError(Exception):
    pass


class InvalidUserDataError(Exception):
    pass


class ProgramNotFoundError(Exception):
    pass


class UserService:

    def __init__(self, db: Session):
        self.db = db
        self.repo = UserRepository(db)

    # Отримання списку
    def list_users(self, skip: int = 0, limit: int = 20) -> list[User]:
        return self.repo.list_users(skip, limit)

    def list_program_assignment_candidates(self) -> list[User]:
        return self.repo.list_program_assignment_candidates()

    # Отримання одного користувача
    def get_user(self, user_id: int) -> User:

        user = self.repo.get_by_id(user_id)

        if user is None:
            raise UserNotFoundError("Користувача не знайдено")

        return user

    # Перевірка зовнішніх ключів
    def _check_refs(self, values: dict) -> None:

        references = (
            ("role_id", Role, "Роль"),
            ("program_id", Program, "Програма"),
            ("department_id", Department, "Підрозділ"),
        )

        for field, model, name in references:

            value = values.get(field)

            if value is None:
                continue

            exists = self.db.scalar(select(model.id).where(model.id == value))

            if exists is None:
                raise InvalidUserDataError(f"{name} '{value}' не існує")

    # Створення користувача
    def create_user(self, data: UserCreate) -> User:

        if self.repo.get_by_login(data.login):
            raise UserAlreadyExistsError("Такий логін уже існує")

        values = data.model_dump(exclude={"password"})

        self._check_refs(values)

        user = User(**values, password_hash=hash_password(data.password))

        try:
            return self.repo.add(user)

        except IntegrityError as error:
            self.db.rollback()
            raise UserAlreadyExistsError("Конфлікт даних під час створення") from error

    # Редагування користувача
    def update_user(self, user_id: int, data: UserUpdate) -> User:

        user = self.get_user(user_id)

        # Беремо тільки поля, передані клієнтом
        changes = data.model_dump(exclude_unset=True)

        # Обов'язкові поля не можна очистити
        for field in ("login", "role_id", "password"):
            if field in changes and changes[field] is None:
                raise InvalidUserDataError(f"Поле {field} не може бути null")

        # Перевіряємо унікальність нового логіна
        if "login" in changes:
            existing = self.repo.get_by_login(changes["login"])

            if existing and existing.id != user_id:
                raise UserAlreadyExistsError("Такий логін уже існує")

        self._check_refs(changes)

        # Якщо пароль змінився — створюємо новий хеш
        if "password" in changes:
            user.password_hash = hash_password(changes.pop("password"))

        # Змінюємо інші передані поля
        for field, value in changes.items():
            setattr(user, field, value)

        try:
            return self.repo.save(user)

        except IntegrityError as error:
            self.db.rollback()
            raise UserAlreadyExistsError("Конфлікт даних під час оновлення") from error

    # Призначення антикорупційної програми користувачу
    def assign_program(
        self,
        user_id: int,
        program_id: str | None,
    ) -> User:

        # 1. Перевіряємо користувача.
        user = self.get_user(user_id)

        # 2. Якщо передано null,
        # відв'язуємо програму.
        if program_id is None:

            try:
                return self.repo.assign_program(
                    user,
                    None,
                )

            except IntegrityError as error:
                self.db.rollback()

                raise InvalidUserDataError("Не вдалося відв'язати програму") from error

        if user.role_id in ("ADMIN", "KOORD"):
            raise InvalidUserDataError("Адміністраторів і координаторів не можна призначати до програми цим способом")

        if user.program_id not in (None, program_id):
            raise InvalidUserDataError("Користувач уже закріплений за іншою програмою")

        # 3. Шукаємо програму в PostgreSQL.
        program = self.db.get(
            Program,
            program_id,
        )

        if program is None:
            raise ProgramNotFoundError(
                f"Антикорупційну програму " f"'{program_id}' не знайдено"
            )

        # 4. Призначаємо знайдену програму.
        try:
            return self.repo.assign_program(
                user,
                program.id,
            )

        except IntegrityError as error:
            self.db.rollback()

            raise InvalidUserDataError("Не вдалося призначити програму") from error

    # Видалення користувача
    def delete_user(self, user_id: int) -> None:

        user = self.get_user(user_id)

        try:
            self.repo.delete(user)

        except IntegrityError as error:
            self.db.rollback()
            raise UserAlreadyExistsError("Користувач має пов'язані записи") from error
