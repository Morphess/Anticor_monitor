"""Analyze only the immutable document pinned to an accessible submission."""
import hashlib

from app.models.order import Order
from app.services.execution_services import ExecutionService, ExecutionError
from app.services.measure_access import require_visible_measure
from app.services.order_analysis_services import MAX_DOCUMENT_BYTES, OrderAnalysisError


def analysis_input(db, actor, execution_id):
    svc = ExecutionService(db)
    row = svc.get(execution_id)
    measure = require_visible_measure(db, actor, row.measure_id)
    svc.require_read_access(row, actor)
    path, version = svc.get_document(row, actor, which="submitted")
    if version.size_bytes > MAX_DOCUMENT_BYTES:
        raise OrderAnalysisError("Документ перевищує ліміт аналізу", 413)
    if not row.submitted_sha256 or row.submitted_sha256 != version.sha256:
        raise ExecutionError("Версія документа не відповідає поданню", 409)
    # Recheck the bytes actually sent to the model, after storage verification.
    with path.open("rb") as inp:
        content = inp.read(MAX_DOCUMENT_BYTES + 1)
    if len(content) > MAX_DOCUMENT_BYTES:
        raise OrderAnalysisError("Документ перевищує ліміт аналізу", 413)
    if len(content) != version.size_bytes or hashlib.sha256(content).hexdigest() != row.submitted_sha256:
        raise ExecutionError("Вміст документа змінився", 409)
    order = db.get(Order, row.order_id)
    if order is None:
        raise ExecutionError("Наказ подання не знайдено", 409)
    return order, measure, version.original_filename, content, version.id, row.submitted_sha256


def saved_analysis_context(db, actor, execution_id):
    """Authorize before cache lookup; no document read or model request on GET."""
    from app.models.order_version import OrderVersion
    from app.services.order_analysis_services import analysis_fingerprint
    svc = ExecutionService(db)
    row = svc.get(execution_id)
    measure = require_visible_measure(db, actor, row.measure_id)
    svc.require_read_access(row, actor)
    version = db.get(OrderVersion, row.order_version_id) if row.order_version_id else None
    order = db.get(Order, row.order_id) if row.order_id else None
    if (version is None or order is None or version.order_id != row.order_id
            or not row.submitted_sha256 or version.sha256 != row.submitted_sha256):
        raise ExecutionError("Зафіксована версія наказу подання недоступна", 409)
    return version.id, row.submitted_sha256, analysis_fingerprint(order, measure)
