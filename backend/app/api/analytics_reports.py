from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_roles
from app.database.db_connection import get_db
from app.models.user import User
from app.services import analytics_report_service as service

router = APIRouter(prefix="/analytics", tags=["Analytics reports"],
                   dependencies=[Depends(require_roles(*service.VIEW_ROLES))])


class RequestIn(BaseModel):
    topic: str = Field(max_length=200)
    question: str = Field(default="", max_length=4000)
    program_id: str | None = None
    due_on: date | None = None


class ReportIn(BaseModel):
    request_id: int | None = None
    program_id: str | None = None
    title: str = Field(max_length=200)
    findings: str = Field(max_length=20000)
    proposals: str = Field(default="", max_length=20000)


def _run(fn, *args):
    try:
        return fn(*args)
    except service.ReportError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.get("/inbox")
def inbox(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Запити до аналітика і звіти: для керівника — свої запити й отримані звіти, для аналітика — черга."""
    return service.inbox(db, user)


@router.post("/requests", dependencies=[Depends(require_roles(*service.REQUESTER_ROLES))])
def create_request(data: RequestIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Керівник запитує аналітичний звіт."""
    return _run(service.create_request, db, user, data.topic, data.question, data.program_id, data.due_on)


@router.post("/requests/{request_id}/take", dependencies=[Depends(require_roles(*service.AUTHOR_ROLES))])
def take_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Аналітик бере запит у роботу."""
    return _run(service.take_request, db, user, request_id)


@router.post("/reports", dependencies=[Depends(require_roles(*service.AUTHOR_ROLES))])
def create_report(data: ReportIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Аналітик надсилає звіт керівнику; зріз даних додається автоматично."""
    return _run(service.create_report, db, user, data.request_id, data.program_id, data.title,
                data.findings, data.proposals)


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Звіт повністю. Перше відкриття керівником позначає звіт прочитаним."""
    return _run(service.get_report, db, user, report_id)
