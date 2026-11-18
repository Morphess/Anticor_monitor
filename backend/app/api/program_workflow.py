"""HTTP-шар: програми до підрозділів -> підрозділи -> конкретні виконавці."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.programs import ProgramRead
from app.schemas.program_workflow import (
    AssignMeasureIn,
    AssignmentResult,
    CoordinatorRead,
    DepartmentDispatchRead,
    DepartmentScopeRead,
    DispatchDepartmentsIn,
    DispatchDepartmentsOut,
    MeasureAssignmentRead,
    MeasureBriefRead,
    ProgramAccessRead,
    SectionBriefRead,
)
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError

router = APIRouter(prefix="/program-routing", tags=["Program Routing"])


def handle(action):
    try:
        return action()
    except WorkflowError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get(
    "/programs/{program_id}/available-departments",
    response_model=list[DepartmentScopeRead],
)
def available_departments(
    program_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).available_departments(program_id, user))


@router.post("/programs/{program_id}/departments", response_model=DispatchDepartmentsOut)
def send_program(
    program_id: str,
    data: DispatchDepartmentsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).send_to_departments(
        program_id, data.department_ids, user
    ))


@router.get("/my/programs", response_model=list[ProgramAccessRead])
def my_programs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).my_programs(user))


@router.get("/programs/{program_id}", response_model=ProgramRead)
def read_visible_program(
    program_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).visible_program(program_id, user))


@router.get("/programs/{program_id}/sections", response_model=list[SectionBriefRead])
def program_sections(
    program_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).program_sections(program_id, user))


@router.get("/programs/{program_id}/measures", response_model=list[MeasureBriefRead])
def program_measures(
    program_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).program_measures(program_id, user))


@router.get("/my/measures", response_model=list[MeasureBriefRead])
def my_measures(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).my_measures(user))


@router.get(
    "/programs/{program_id}/departments/{department_id}/coordinators",
    response_model=list[CoordinatorRead],
)
def get_coordinators(
    program_id: str,
    department_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).department_coordinators(
        program_id, department_id, user
    ))


@router.get(
    "/programs/{program_id}/departments/{department_id}/executors",
    response_model=list[CoordinatorRead],
)
def get_executors(
    program_id: str,
    department_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).department_executors(
        program_id, department_id, user
    ))


@router.post("/measures/{measure_id}/assign", response_model=AssignmentResult)
def assign_measure(
    measure_id: str,
    data: AssignMeasureIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).assign(
        measure_id, data.department_id, data.user_id, user
    ))


@router.get("/measures/{measure_id}/assignments", response_model=list[MeasureAssignmentRead])
def measure_assignments(
    measure_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return handle(lambda: ProgramWorkflowService(db).list_assignments(measure_id, user))


@router.delete("/measures/{measure_id}/assign/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unassign_measure(
    measure_id: str,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    handle(lambda: ProgramWorkflowService(db).revoke(measure_id, user_id, user))
