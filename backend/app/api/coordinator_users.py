from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.program_workflow import ProgramAccessRead
from app.schemas.users import UserRead
from pydantic import BaseModel, ConfigDict, Field
from app.services.user_services import InvalidUserDataError, UserNotFoundError, UserService
from app.services.program_workflow_services import ProgramWorkflowService


router = APIRouter(prefix="/coordinator/users", tags=["Coordinator users"])


class CoordinatorProgramAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")
    program_id: str = Field(min_length=1, max_length=50)


def _available_programs(db: Session, coordinator: User) -> list[dict]:
    return ProgramWorkflowService(db).my_programs(coordinator)


@router.get("/", response_model=list[UserRead])
def list_assignment_candidates(
    db: Session = Depends(get_db),
    coordinator: User = Depends(require_roles("KOORD")),
):
    return UserService(db).list_program_assignment_candidates()


@router.get("/programs", response_model=list[ProgramAccessRead])
def list_coordinator_programs(
    db: Session = Depends(get_db),
    coordinator: User = Depends(require_roles("KOORD")),
):
    return _available_programs(db, coordinator)


@router.patch("/{user_id}/program", response_model=UserRead)
def assign_coordinator_program(
    user_id: int,
    data: CoordinatorProgramAssign,
    db: Session = Depends(get_db),
    coordinator: User = Depends(require_roles("KOORD")),
):
    if data.program_id not in {program["id"] for program in _available_programs(db, coordinator)}:
        raise HTTPException(status_code=403, detail="Ця програма не належить до повноважень координатора.")
    try:
        return UserService(db).assign_program(user_id, data.program_id)
    except UserNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except InvalidUserDataError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
