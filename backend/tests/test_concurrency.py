"""Одночасні дії над одним записом: пройти має рівно одна. Запускається лише на PostgreSQL
(SQLite не дає справжньої паралельності)."""
import threading

import pytest
from sqlalchemy import func, select

from app.db import engine, session_scope
from app.models import JournalEntry
from app.services import monitor, workflow
from app.services.rules import WorkflowError
from app.utils import now_utc

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="потрібен PostgreSQL")
KOORD = {"id": "U-002", "role": "KOORD"}


def test_two_decisions_at_once_only_one_wins(db):
    m = next(x for x in monitor.snapshot()["measures"] if x["review_state"] == "submitted")
    db.commit()
    started = now_utc()
    results, barrier = [], threading.Barrier(8)

    def worker(i: int) -> None:
        with session_scope():
            barrier.wait()
            try:
                workflow.decide(KOORD, m["id"], "2026-H1", "approve" if i % 2 else "return", "Доопрацюйте")
                results.append("ok")
            except WorkflowError:
                results.append("refused")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["ok"] + ["refused"] * 7
    with session_scope() as s:
        decisions = s.scalar(select(func.count()).select_from(JournalEntry).where(
            JournalEntry.object == "vykonannia", JournalEntry.object_id == m["id"],
            JournalEntry.action.in_(("погоджено координатором", "повернуто на доопрацювання")),
            JournalEntry.at >= started))
    assert decisions == 1
