from getpass import getpass
from sqlalchemy import select

from app.database.db_connection import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.core.security import hash_password


def create_admin():

    # Вводимо логін та пароль
    login = input("Логін адміністратора: ").strip()
    password = getpass("Пароль адміністратора: ")

    if not login or len(password) < 12:
        print("Вкажи логін і пароль від 12 символів")
        return

    # Підключаємося до PostgreSQL
    with SessionLocal() as db:

        # Перевіряємо наявність ролі ADMIN
        role = db.get(Role, "ADMIN")

        if role is None:
            print("Роль ADMIN не знайдена")
            return

        # Перевіряємо чи не існує користувач
        existing_user = db.scalar(select(User).where(User.login == login))

        if existing_user:
            print("Користувач із таким логіном уже існує")
            return

        # Створюємо користувача
        admin = User(
            login=login, password_hash=hash_password(password), role_id="ADMIN"
        )

        db.add(admin)
        db.commit()

        print("Адміністратора успішно створено!")


if __name__ == "__main__":
    create_admin()
