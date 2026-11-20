"""Read-only preflight for Anticor Monitor Alembic revision b6f41c153c28.

Run from Anticor_monitor/backend:
    set DB_ENV=local
    python check_migration_b6f41c.py

Does not execute DDL/DML. Refuses non-local database hosts.
"""
from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.core.config import settings


def main() -> None:
    url = make_url(str(settings.DATABASE_URL))
    print(f"Database: host={url.host!r}, port={url.port!r}, name={url.database!r}")
    if (url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("STOP: DB host is not local. No queries performed.")

    engine = create_engine(url)
    try:
        existing_tables = set(inspect(engine).get_table_names())
        with engine.connect() as conn:
            print("\n--- Alembic revision(s) in database ---")
            if "alembic_version" in existing_tables:
                versions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
                print(", ".join(versions) if versions else "No version rows")
            else:
                print("alembic_version table missing")

            print("\n--- Existing records ---")
            for table in ["risks", "measures", "programs", "orders", "evidences"]:
                if table in existing_tables:
                    n = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()
                    print(f"{table}: {n}")
                else:
                    print(f"{table}: TABLE MISSING")

            print("\n--- New tables already present (would collide with CREATE TABLE) ---")
            for table in [
                "analytics_requests", "management_decisions", "order_versions",
                "program_departments", "analytics_reports", "invalid_order_references",
                "measure_assignments", "order_change_alerts", "order_change_alert_reads",
            ]:
                if table in existing_tables:
                    print(f"PRESENT: {table}")

            if {"risks", "measures"} <= existing_tables:
                print("\n--- Risks whose program cannot be inferred uniquely from measures ---")
                rows = conn.execute(text("""
                    SELECT r.id, count(DISTINCT m.program_id) AS program_count,
                           coalesce(string_agg(DISTINCT m.program_id, ', '), '') AS candidate_programs
                    FROM risks r
                    LEFT JOIN measures m ON m.risk_id = r.id
                    GROUP BY r.id
                    HAVING count(DISTINCT m.program_id) <> 1
                    ORDER BY r.id LIMIT 20
                """)).all()
                if rows:
                    for risk_id, count, candidates in rows:
                        print(f"RISK {risk_id}: {count} candidate programs [{candidates}]")
                    print("BLOCKER: these risks need an explicit data decision before NOT NULL.")
                else:
                    print("None (association via measures is single-valued for each risk).")

            if "orders" in existing_tables:
                print("\n--- Duplicate order numbers (cannot add UNIQUE constraint) ---")
                rows = conn.execute(text("""
                    SELECT number, count(*) AS duplicates
                    FROM orders GROUP BY number HAVING count(*) > 1
                    ORDER BY count(*) DESC, number LIMIT 20
                """)).all()
                if rows:
                    for number, n in rows:
                        print(f"NUMBER {number!r}: {n} rows")
                    print("BLOCKER: numbers must be reconciled before UNIQUE constraint.")
                else:
                    print("None.")

                cols = {c["name"] for c in inspect(conn).get_columns("orders")}
                if "measure_id" in cols:
                    n = conn.execute(text("SELECT count(*) FROM orders WHERE measure_id IS NOT NULL")).scalar_one()
                    print(f"\norders.measure_id populated rows at risk of losing link: {n}")
                else:
                    print("\norders.measure_id not present.")

            if "evidences" in existing_tables:
                cols = {c["name"] for c in inspect(conn).get_columns("evidences")}
                if "source_url" in cols:
                    n = conn.execute(text("""
                        SELECT count(*) FROM evidences
                        WHERE source_url IS NOT NULL AND btrim(source_url) <> ''
                    """)).scalar_one()
                    print(f"\nevidences.source_url populated rows at risk of loss: {n}")
                else:
                    print("\nevidences.source_url not present.")
    finally:
        engine.dispose()
    print("\nDONE: read-only checks; no database changes were made.")


if __name__ == "__main__":
    main()
