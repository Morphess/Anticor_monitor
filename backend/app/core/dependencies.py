import jwt

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.db_connection import get_db
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


# Отримати авторизованого користувача
def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:

    try:
        data = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )

        user_id = int(data["sub"])

    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise HTTPException(
            status_code=401,
            detail="Невірний або прострочений токен",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Користувача не знайдено",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.role_id == "ANAL":
        raise HTTPException(status_code=403, detail="Роль аналітика більше не використовується")

    db.info["audit_actor_id"] = user.id

    return user


# Перевірка прав адміністратора
def require_admin(user: User = Depends(get_current_user)) -> User:

    if user.role_id != "ADMIN":
        raise HTTPException(status_code=403, detail="Недостатньо прав")

    return user


# Перевірка, що роль користувача входить до дозволених
def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role_id not in roles:
            raise HTTPException(status_code=403, detail="Недостатньо прав")
        return user

    return checker
