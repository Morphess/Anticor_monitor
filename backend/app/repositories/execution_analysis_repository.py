from sqlalchemy import func, select
from app.models.execution_analysis import ExecutionAnalysis


class ExecutionAnalysisRepository:
    def __init__(self, db):
        self.db = db

    def latest(self, execution_id, version_id, digest, input_digest):
        return self.db.scalar(select(ExecutionAnalysis).where(
            ExecutionAnalysis.execution_id == execution_id,
            ExecutionAnalysis.order_version_id == version_id,
            ExecutionAnalysis.submitted_sha256 == digest,
            ExecutionAnalysis.input_sha256 == input_digest,
        ).order_by(ExecutionAnalysis.analysis_id.desc()).limit(1))

    def try_lock(self, execution_id):
        # PostgreSQL transaction lock: released by commit, rollback or disconnect.
        return self.db.scalar(select(func.pg_try_advisory_xact_lock(50_050, execution_id)))

    def save(self, execution_id, version_id, digest, input_digest, actor_id, result):
        row = ExecutionAnalysis(execution_id=execution_id, order_version_id=version_id,
            submitted_sha256=digest, input_sha256=input_digest,
            created_by_user_id=actor_id, **result.model_dump())
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row
