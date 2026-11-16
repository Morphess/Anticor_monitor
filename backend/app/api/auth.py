from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.repositories.auth import SqlAlchemyAuthRepository
from app.schemas.auth import LoginRequest, LoginResponse
from app.services.auth_service import authenticate_user


router = APIRouter(prefix="/auth", tags=["API Auth"])


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    repository = SqlAlchemyAuthRepository(db)

    authenticated = authenticate_user(
        request.login,
        request.password.get_secret_value(),
        repository,
    )

    if not authenticated:
        raise HTTPException(
            status_code=401,
            detail="Невірний логін або пароль",
        )

    return LoginResponse(authenticated=True)
