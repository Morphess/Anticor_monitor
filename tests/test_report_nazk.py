import os
import unittest
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1/unused")
os.environ.setdefault("JWT_SECRET_KEY", "synthetic-test-key-for-hs256-at-least-32-bytes")

from pydantic import ValidationError

from app.schemas.execution import ExecutionSubmit
from app.schemas.report_portal import (
    PortalHalfYearReport, ReportMeasureRow, ReportRisk, ReportSectionBlock, ReportSummary,
)
from app.services.report_generation_service import csv_export, period_label, planned_deadline, print_html


class ReportNazkTests(unittest.TestCase):
    def test_period_label(self):
        self.assertEqual(period_label("2026-H1"), "Звіт за перше півріччя 2026 року")
        self.assertEqual(period_label("2026-H2"), "Звіт за друге півріччя 2026 року")

    def test_planned_deadline(self):
        dated = SimpleNamespace(deadline_type="date", deadline_on=date(2026, 3, 31), deadline_description="2026-03-31")
        self.assertEqual(planned_deadline(dated), "31.03.2026")
        ongoing = SimpleNamespace(deadline_type="ongoing", deadline_on=None, deadline_description="")
        self.assertEqual(planned_deadline(ongoing), "Постійно")

    def test_submit_requires_result_description(self):
        base = {"measure_id": "Z-01", "period": "2026-H1", "order_number": "45/2026"}
        with self.assertRaises(ValidationError):
            ExecutionSubmit(**base)
        with self.assertRaises(ValidationError):
            ExecutionSubmit(**base, result_description="коротко")
        with self.assertRaises(ValidationError):
            ExecutionSubmit(**base, result_description="Проведено навчання для 25 осіб", outcome_status="not_completed")
        ok = ExecutionSubmit(**base, result_description="Проведено навчання для 25 осіб", indicator_actual=25)
        self.assertEqual(ok.outcome_status, "completed")

    def _report(self):
        risk = ReportRisk(risk_id="KR01", sphere="Закупівлі", title="Змова учасників", description="Опис ризику")
        rows = {
            1: ReportMeasureRow(measure_id="Z-01", sequence_number=1, measure_description="Затвердити порядок",
                                responsible_department="Департамент 1", planned_deadline="31.03.2026",
                                factual_date=date(2026, 3, 20), execution_status="Виконано",
                                result_description="Порядок затверджено наказом № 45"),
            2: ReportMeasureRow(measure_id="Z-13", sequence_number=1, measure_description="Перевіряти тендери",
                                responsible_department="Департамент 2", completion_indicator="100 % перевірок",
                                execution_status="Не виконано", result_description="", risk_id="KR01", risk=risk),
            3: ReportMeasureRow(measure_id="Z-40", sequence_number=1, measure_description="Навчання",
                                execution_status="Виконано", result_description="Проведено", participants_count=25),
        }
        sections = [ReportSectionBlock(section_id=f"R{n}", number=n, title=f"Розділ {n}", measures=[rows[n]])
                    for n in (1, 2, 3)]
        return PortalHalfYearReport(
            program_id="P1", program_title="Програма", organization_name="Умовне відомство",
            period_label=period_label("2026-H1"), period="2026-H1", period_start=date(2026, 1, 1),
            period_end=date(2026, 6, 30), as_of=date(2026, 6, 30), is_preliminary=False,
            generated_at="2026-07-01T00:00:00Z", scope="program", sections=sections, summary=ReportSummary(total=3),
        )

    def test_print_html_has_nazk_structure(self):
        page = print_html(self._report())
        for text in ("Звіт за перше півріччя 2026 року", "Орган:", "Умовне відомство", "Сфера ризику",
                     "Змова учасників", "Індикатор виконання", "Кількість осіб, які взяли участь у навчанні",
                     "Запланований строк виконання заходу", "st-done", "st-not"):
            self.assertIn(text, page)

    def test_csv_has_nazk_columns(self):
        data = csv_export(self._report()).decode("utf-8-sig")
        header = data.splitlines()[0]
        for column in ("Запланований строк виконання заходу", "Сфера ризику", "Індикатор виконання",
                       "Кількість осіб, які взяли участь у навчанні"):
            self.assertIn(column, header)
        self.assertIn("Змова учасників", data)


if __name__ == "__main__":
    unittest.main()
