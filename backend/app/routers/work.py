"""Дії: внесення інформації виконавцем, погодження координатором, матеріали, строки, індикатори ризиків."""
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from ..auth import require_role
from ..services import monitor, workflow
from ..services.rules import WorkflowError
from ..utils import parse_date, parse_float
from ..web import flash, redirect

router = APIRouter(include_in_schema=False)
executor = require_role("VYK")
coordinator = require_role("KOORD")


def _run(http: Request, ok: str, action, *args, **kwargs) -> None:
    try:
        action(*args, **kwargs)
        flash(http, ok)
    except WorkflowError as e:
        flash(http, str(e), "error")


@router.post("/measures/{measure_id}/execution")
def save_execution(request: Request, measure_id: str, status: str = Form(""), actual_date: str = Form(""),
                   result_text: str = Form(""), indicator_fact: str = Form(""), action: str = Form("save"),
                   user: dict = Depends(executor)):
    submit = action == "submit"
    _run(request, "Подано на погодження координатору" if submit else "Збережено",
         workflow.save_execution, user, measure_id, monitor.current_period(), status=status,
         actual_date=parse_date(actual_date), result_text=result_text,
         indicator_fact=parse_float(indicator_fact), submit=submit, request=request)
    return redirect(f"/measures/{measure_id}")


@router.post("/measures/{measure_id}/evidence")
def add_evidence(request: Request, measure_id: str, type_: str = Form("", alias="type"), name: str = Form(""),
                 doc_date: str = Form(""), link: str = Form(""), file: UploadFile | None = File(None),
                 user: dict = Depends(executor)):
    _run(request, "Підтвердний матеріал додано. Змінити або видалити його вже не можна.",
         workflow.add_evidence, user, measure_id, type_=type_, name=name, doc_date=parse_date(doc_date),
         link=link, upload=file, request=request)
    return redirect(f"/measures/{measure_id}")


@router.post("/measures/{measure_id}/decision")
def decide(request: Request, measure_id: str, action: str = Form(""), comment: str = Form(""),
           user: dict = Depends(coordinator)):
    _run(request, "Погоджено" if action == "approve" else "Повернуто на доопрацювання",
         workflow.decide, user, measure_id, monitor.current_period(), action, comment, request)
    return redirect(f"/measures/{measure_id}")


@router.post("/measures/{measure_id}/postpone")
def postpone(request: Request, measure_id: str, new_date: str = Form(""), reason: str = Form(""),
             user: dict = Depends(coordinator)):
    _run(request, "Внутрішній строк змінено. Строк у програмі залишився тим самим.",
         workflow.postpone, user, measure_id, parse_date(new_date), reason, request)
    return redirect(f"/measures/{measure_id}")


@router.post("/risks/{risk_id}/measurement")
def add_measurement(request: Request, risk_id: str, on: str = Form(""), value: str = Form(""),
                    source: str = Form(""), user: dict = Depends(coordinator)):
    _run(request, "Вимірювання внесено", workflow.add_risk_measurement, user, risk_id, parse_date(on),
         parse_float(value), source, request)
    return redirect(f"/risks/{risk_id}")
