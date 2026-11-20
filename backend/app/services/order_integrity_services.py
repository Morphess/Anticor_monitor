"""Manual/scheduled server-side SHA-256 scan. Run from Windows Task Scheduler/cron."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.execution import Execution
from app.models.order import Order
from app.models.order_version import OrderVersion
from app.services.execution_services import ExecutionService


class OrderIntegrityService:
    def __init__(self, db: Session):
        self.db = db
        self.executions = ExecutionService(db)

    def scan(self) -> dict[str, int]:
        """Detect changed latest version or tampered bytes; invalidate approved status.

        Does not erase pinned hash, reviewer identity or action-log history.
        """
        scanned = changed = 0
        # Materialize order ids so locking order rows cannot rearrange this query.
        order_ids = list(self.db.scalars(select(Order.id).order_by(Order.id)))
        for order_id in order_ids:
            # Lock the order first to serialize with version uploads and submission.
            self.db.scalar(select(Order).where(Order.id == order_id).with_for_update())
            rows = list(self.db.scalars(select(Execution).where(
                Execution.order_id == order_id,
                Execution.order_version_id.is_not(None),
            ).with_for_update()))
            for row in rows:
                scanned += 1
                was_flagged = row.document_changed
                if self.executions.invalidate_if_changed(row) and not was_flagged:
                    changed += 1
            self.db.commit()
        return {"scanned": scanned, "new_warnings": changed}
