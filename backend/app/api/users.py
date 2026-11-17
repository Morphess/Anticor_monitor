from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.core.dependencies import require_admin

from app.models.user import User
from app.schemas.users import UserCreate, UserRead, UserUpdate, UserProgramAssign
from app.services.user_services import (
    UserService,
    UserNotFoundError,
    UserAlreadyExistsError,
    InvalidUserDataError,
    ProgramNotFoundError,
)


# Усі маршрути цього роутера доступні ADMIN
router = APIRouter(
    prefix="/users", tags=["Users"], dependencies=[Depends(require_admin)]
)


# CREATE — створення користувача
@router.post("/", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    try:
        return UserService(db).create_user(data)

    except InvalidUserDataError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    except UserAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


# READ — список користувачів
@router.get("/", response_model=list[UserRead])
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return UserService(db).list_users(skip, limit)


# READ — один користувач
@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)):
    try:
        return UserService(db).get_user(user_id)

    except UserNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


# UPDATE — редагування користувача
@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    # Не дозволяємо адміністратору
    # випадково забрати власні права
    if user_id == admin.id and data.role_id not in (None, "ADMIN"):
        raise HTTPException(
            status_code=409, detail="Не можна змінити власну роль ADMIN"
        )

    try:
        return UserService(db).update_user(user_id, data)

    except UserNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    except InvalidUserDataError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    except UserAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


# UPDATE — призначення антикорупційної програми користувачу
@router.patch(
    "/{user_id}/program",
    response_model=UserRead,
)
def assign_user_program(
    user_id: int,
    data: UserProgramAssign,
    db: Session = Depends(get_db),
):

    try:
        return UserService(db).assign_program(
            user_id=user_id,
            program_id=data.program_id,
        )

    except UserNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    except ProgramNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    except InvalidUserDataError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error


# DELETE — видалення користувача
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)
):
    # Забороняємо адміністратору
    # видаляти власний обліковий запис
    if user_id == admin.id:
        raise HTTPException(status_code=409, detail="Не можна видалити власний акаунт")

    try:
        UserService(db).delete_user(user_id)

    except UserNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    except UserAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
