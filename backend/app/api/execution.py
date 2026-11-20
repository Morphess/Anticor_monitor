"""One independent submission, document and review decision per executor."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database.db_connection import get_db
from app.models.user import User
from app.schemas.execution import ExecutionSubmit, ExecutionReject, ExecutionRead, ExecutionStatus
from app.services.execution_services import ExecutionService, ExecutionError
from app.services.measure_access import (
    require_execution_actor, require_executor, require_department_coordinator,
    require_visible_measure, visible_measure_ids,
)
from app.services.program_workflow_services import ProgramWorkflowService, WorkflowError

router = APIRouter(prefix='/executions', tags=['Executions'])


def _http(exc):
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post('/submit', response_model=ExecutionRead, status_code=201,
             summary='VYK: submit own order number')
def submit_execution(data: ExecutionSubmit, db: Session = Depends(get_db),
                     actor: User = Depends(require_executor)):
    try:
        svc = ExecutionService(db)
        return svc.as_read(svc.submit(data, actor))
    except ExecutionError as exc:
        raise _http(exc) from exc


@router.get('/', response_model=list[ExecutionRead], summary='All accessible submissions, per executor')
def list_executions(measure_id: str | None = None, period: str | None = None,
                    status: ExecutionStatus | None = None,
                    offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                    db: Session = Depends(get_db), actor: User = Depends(require_execution_actor)):
    if measure_id is not None:
        require_visible_measure(db, actor, measure_id)
        ids = {measure_id}
    else:
        ids = visible_measure_ids(db, actor)
    dept_ids = None
    by_user = None
    if actor.role_id == 'VYK':
        by_user = actor.id
    elif actor.role_id == 'KOORD':
        if not actor.department_id:
            return []
        try:
            dept_ids = ProgramWorkflowService(db).tree.descendants(actor.department_id)
        except WorkflowError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    svc = ExecutionService(db)
    return [svc.as_read(row) for row in svc.repo.list(
        measure_ids=ids, period=period, status=status, department_ids=dept_ids,
        submitted_by=by_user, offset=offset, limit=limit,
    )]


@router.get('/{execution_id}', response_model=ExecutionRead, summary='Individual submission')
def get_execution(execution_id: int, db: Session = Depends(get_db),
                  actor: User = Depends(require_execution_actor)):
    svc = ExecutionService(db)
    try:
        row = svc.get(execution_id)
        require_visible_measure(db, actor, row.measure_id)
        svc.require_read_access(row, actor)
        return svc.as_read(row)
    except ExecutionError as exc:
        raise _http(exc) from exc


@router.get('/{execution_id}/document', summary='Verified order document, access checked')
def get_document(execution_id: int, which: str = Query('submitted', pattern='^(submitted|current)$'),
                 db: Session = Depends(get_db), actor: User = Depends(require_execution_actor)):
    svc = ExecutionService(db)
    try:
        row = svc.get(execution_id)
        require_visible_measure(db, actor, row.measure_id)
        path, version = svc.get_document(row, actor, which=which)
        return FileResponse(path, media_type=version.content_type,
                            filename=version.original_filename,
                            content_disposition_type='inline' if version.content_type == 'application/pdf' else 'attachment')
    except ExecutionError as exc:
        raise _http(exc) from exc


@router.post('/{execution_id}/approve', response_model=ExecutionRead,
             summary='KOORD: approve exactly this executor submission')
def approve(execution_id: int, db: Session = Depends(get_db),
            actor: User = Depends(require_department_coordinator)):
    svc = ExecutionService(db)
    try:
        row = svc.get(execution_id)
        require_visible_measure(db, actor, row.measure_id)
        return svc.as_read(svc.review(execution_id, actor, approve=True))
    except ExecutionError as exc:
        raise _http(exc) from exc


@router.post('/{execution_id}/reject', response_model=ExecutionRead,
             summary='KOORD: reject this submission with required reason')
def reject(execution_id: int, data: ExecutionReject,
           db: Session = Depends(get_db), actor: User = Depends(require_department_coordinator)):
    svc = ExecutionService(db)
    try:
        row = svc.get(execution_id)
        require_visible_measure(db, actor, row.measure_id)
        return svc.as_read(svc.review(execution_id, actor, approve=False, reason=data.reason))
    except ExecutionError as exc:
        raise _http(exc) from exc
