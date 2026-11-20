"""One measure-level status from independent, currently assigned executor submissions.

Only ALL active assigned executors approved => a measure is completed. Historic
submissions from revoked assignments remain auditable but do not count toward KPIs.
This function is deliberately pure for use by reports, Risk Flags, and KER dashboards.
"""
from collections import defaultdict
from types import SimpleNamespace
from sqlalchemy import select
from app.models.program_workflow import MeasureAssignment


def assignments_for(db, measure_ids: set[str]) -> dict[str, set[int]]:
    if not measure_ids:
        return {}
    result = defaultdict(set)
    for mid, user_id in db.execute(
        select(MeasureAssignment.measure_id, MeasureAssignment.user_id).where(
            MeasureAssignment.measure_id.in_(measure_ids)
        )
    ):
        result[mid].add(user_id)
    return dict(result)


def summary_for(measure_id: str, period: str, rows: list, users: set[int]):
    if not users:
        return None
    active = {row.submitted_by_user_id: row for row in rows
              if row.measure_id == measure_id and row.period == period
              and row.submitted_by_user_id in users}
    if not active:
        return None
    approved = [row for row in active.values()
                if row.status == 'approved' and not row.document_changed
                and row.order_version_id is not None and row.submitted_sha256]
    pending = [row for row in active.values() if row.status == 'pending']
    rejected = [row for row in active.values() if row.status == 'rejected']
    complete = len(approved) == len(users)
    status = ('approved' if complete else 'pending' if pending or approved else 'rejected'
              if rejected else 'pending')
    reported = [r for r in approved if (r.outcome_status or 'completed') in {'completed', 'vykonano'}]
    outcome = ('completed' if complete and len(reported) == len(users) else
               'partial' if complete else 'in_progress')
    indicators = {r.indicator_actual for r in approved}
    dates = [r.completed_on for r in approved if r.completed_on is not None]
    descriptions = [r.result_description for r in approved if r.result_description]
    submissions = [r.submitted_at for r in active.values() if r.submitted_at is not None]
    return SimpleNamespace(
        measure_id=measure_id, period=period, status=status, outcome_status=outcome,
        approved_by_coordinator=complete, document_changed=any(r.document_changed for r in active.values()),
        submitted_at=max(submissions) if submissions else None,
        completed_on=max(dates) if complete and len(dates) == len(users) else None,
        result_description='; '.join(descriptions) if complete else '',
        indicator_actual=next(iter(indicators)) if complete and len(indicators) == 1 else None,
        approved_count=len(approved), assigned_count=len(users),
        pending_count=len(pending), rejected_count=len(rejected),
    )


def summaries(db, measure_ids: set[str], period: str, executions: list) -> dict:
    users = assignments_for(db, measure_ids)
    grouped = defaultdict(list)
    for execution in executions:
        grouped[execution.measure_id].append(execution)
    return {mid: result for mid in measure_ids
            if (result := summary_for(mid, period, grouped[mid], users.get(mid, set()))) is not None}
