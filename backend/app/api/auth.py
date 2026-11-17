from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.user import User
from app.core.security import (
    verify_password,
    create_access_token,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# Вхід користувача
@router.post("/token")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Шукаємо користувача за логіном
    user = db.scalar(select(User).where(User.login == form.username))

    # Перевіряємо користувача і пароль
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Невірний логін або пароль")

    # Повертаємо JWT-токен
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}
