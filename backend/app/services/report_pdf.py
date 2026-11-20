"""PDF export of an immutable portal report snapshot (no database queries).

This module intentionally loads ReportLab only while exporting. FastAPI can start
without ReportLab, but the endpoint will return an actionable 503 until installed.
"""
from __future__ import annotations

from html import escape
from io import BytesIO
import os
from pathlib import Path

from app.schemas.report_portal import PortalHalfYearReport


class PDFExportError(Exception):
    """A PDF cannot be generated (missing dependency or Unicode font)."""


def _font_paths() -> tuple[Path, Path]:
    """Find Unicode TTF fonts; never ship licensed font files with the project."""
    user_regular = os.getenv("REPORT_PDF_FONT", "").strip()
    user_bold = os.getenv("REPORT_PDF_FONT_BOLD", "").strip()
    if user_regular:
        regular = Path(user_regular).expanduser()
        bold = Path(user_bold).expanduser() if user_bold else regular
        if not regular.is_file() or not bold.is_file():
            raise PDFExportError("Шрифт для PDF не знайдено. Перевір REPORT_PDF_FONT та REPORT_PDF_FONT_BOLD.")
        return regular, bold

    candidates = (
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    )
    for regular, bold in candidates:
        r, b = Path(regular), Path(bold)
        if r.is_file() and b.is_file():
            return r, b
    raise PDFExportError(
        "Не знайдено Unicode TTF-шрифт для українського PDF. "
        "Встанови Arial або DejaVu Sans чи встанови REPORT_PDF_FONT."
    )


def _safe_text(value: object, *, multiline: bool = False) -> str:
    """Escape untrusted program/measure text before using ReportLab Paragraph."""
    text = escape("" if value is None else str(value), quote=True)
    return text.replace("\n", "<br/>") if multiline else text


def pdf_export(
    snapshot: PortalHalfYearReport, *, report_id: int, version: int
) -> bytes:
    """Render a saved report snapshot as A4 landscape PDF with embedded Ukrainian font."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            HRFlowable, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        )
    except ImportError as exc:
        raise PDFExportError(
            "Для завантаження PDF необхідний ReportLab. "
            "У backend/venv виконай: python -m pip install reportlab"
        ) from exc

    regular, bold = _font_paths()
    try:
        registered = set(pdfmetrics.getRegisteredFontNames())
        if "AnticorPDFRegular" not in registered:
            pdfmetrics.registerFont(TTFont("AnticorPDFRegular", str(regular)))
        if "AnticorPDFBold" not in registered:
            pdfmetrics.registerFont(TTFont("AnticorPDFBold", str(bold)))
        pdfmetrics.registerFontFamily(
            "AnticorPDFRegular", normal="AnticorPDFRegular", bold="AnticorPDFBold"
        )
    except Exception as exc:
        raise PDFExportError(f"Не вдалося підключити Unicode-шрифт PDF: {exc}") from exc

    navy = colors.HexColor("#22252A")
    muted = colors.HexColor("#59616A")
    accent = colors.HexColor("#F26B38")
    pale = colors.HexColor("#F4F5F6")
    line = colors.HexColor("#D9DDE1")
    page = landscape(A4)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=page, rightMargin=30, leftMargin=30,
        topMargin=35, bottomMargin=42,
        title=f"Звіт №{report_id} - {snapshot.period}",
        author="Anticor_monitor",
    )
    width = document.width
    text_style = ParagraphStyle(
        "BodyUA", fontName="AnticorPDFRegular", fontSize=8, leading=11,
        textColor=navy, wordWrap="LTR", splitLongWords=1,
        spaceAfter=0,
    )
    muted_style = ParagraphStyle(
        "MutedUA", parent=text_style, textColor=muted, fontSize=8,
    )
    title_style = ParagraphStyle(
        "TitleUA", parent=text_style, fontName="AnticorPDFBold",
        fontSize=16, leading=21, spaceAfter=11,
    )
    heading_style = ParagraphStyle(
        "HeadingUA", parent=text_style, fontName="AnticorPDFBold",
        fontSize=11, leading=15, spaceBefore=14, spaceAfter=7,
    )
    header_style = ParagraphStyle(
        "HeaderUA", parent=text_style, fontName="AnticorPDFBold", fontSize=7.5,
        leading=10, textColor=navy,
    )
    cell_style = ParagraphStyle(
        "CellUA", parent=text_style, fontSize=7.5, leading=10,
    )
    center_style = ParagraphStyle(
        "CenterUA", parent=cell_style, alignment=TA_CENTER,
    )

    def paragraph(value: object, style=cell_style):
        return Paragraph(_safe_text(value, multiline=True) or "—", style)

    flow = [
        Paragraph(_safe_text(snapshot.period_label or "Звіт про виконання антикорупційної програми"), title_style),
        Paragraph("<b>Орган:</b> " + _safe_text(snapshot.organization_name or "—"), text_style),
        Paragraph(_safe_text(snapshot.program_title), heading_style),
    ]
    status = "Попередній звіт" if snapshot.is_preliminary else "Завершений звітний період"
    attributes = (
        f"Період: {_safe_text(snapshot.period)}  ·  "
        f"Дата зрізу: {_safe_text(snapshot.as_of)}  ·  "
        f"{status}  ·  "
        f"Звіт №{report_id}, версія {version}"
    )
    flow.extend([
        Paragraph(attributes, muted_style),
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=1, color=accent),
        Spacer(1, 10),
    ])
    summary = snapshot.summary
    summary_items = [
        ("Усього заходів", summary.total),
        ("Виконано", summary.completed),
        ("Частково", summary.partial),
        ("Не виконано", summary.not_completed),
        ("Не погоджено", summary.unapproved),
    ]
    metric_width = width / len(summary_items)
    summary_data = [[
        Paragraph(_safe_text(label), muted_style) for label, _ in summary_items
    ], [
        Paragraph(_safe_text(value), ParagraphStyle(
            f"NumberUA{index}", parent=text_style, fontName="AnticorPDFBold",
            fontSize=13, leading=17,
        )) for index, (_, value) in enumerate(summary_items)
    ]]
    metric_table = Table(summary_data, colWidths=[metric_width] * len(summary_items), hAlign="LEFT")
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, line),
    ]))
    flow.extend([metric_table, Spacer(1, 6)])

    status_fill = {
        "Виконано": colors.HexColor("#C6EFCE"),
        "Частково виконано": colors.HexColor("#FFEB9C"),
        "Не виконано": colors.HexColor("#FFC7CE"),
    }
    risk_fill = colors.HexColor("#E8EEF5")
    col_widths = [width * f for f in (.05, .37, .11, .13, .34)]

    def labelled(pairs):
        text = "<br/>".join(
            f"<b>{_safe_text(label)}</b><br/>{_safe_text(value, multiline=True)}"
            for label, value in pairs if value
        )
        return Paragraph(text or "—", cell_style)

    def measure_cell(measure, number):
        name = {2: "Найменування заходу", 3: "Навчальний захід"}.get(number, "Опис заходу")
        who = ("Відповідальні виконавці" if number == 2 else
               "Найменування структурного підрозділу, відповідального за виконання заходу")
        pairs = [(name, measure.measure_description),
                 (who, measure.responsible_department or measure.responsible_department_id),
                 ("Запланований строк виконання заходу", measure.planned_deadline)]
        if number == 2:
            pairs.append(("Індикатор виконання", measure.completion_indicator))
        return labelled(pairs)

    for section in snapshot.sections:
        flow.append(Paragraph(_safe_text(section.title), heading_style))
        last = ("Кількість осіб, які взяли участь у навчанні" if section.number == 3
                else "Опис результату виконання заходу або пояснення причин невиконання")
        headers = ["№", "Навчальний захід" if section.number == 3 else "Захід",
                   "Фактичний строк виконання", "Стан виконання", last]
        data = [[paragraph(h, header_style) for h in headers]]
        styles = []
        groups = []
        if section.number == 2:
            index = {}
            for measure in section.measures:
                key = measure.risk.risk_id if measure.risk else None
                if key not in index:
                    index[key] = len(groups)
                    groups.append((measure.risk, []))
                groups[index[key]][1].append(measure)
        else:
            groups = [(None, list(section.measures))]
        for risk, measures in groups:
            if risk is not None:
                data.append([labelled([("Сфера ризику", risk.sphere), ("Назва ризику", risk.title),
                                       ("Опис ризику", risk.description)]), "", "", "", ""])
                r = len(data) - 1
                styles += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), risk_fill)]
            for measure in measures:
                if section.number == 3:
                    tail = measure.participants_count if measure.participants_count is not None else "—"
                else:
                    tail = measure.result_description or "—"
                if measure.warnings:
                    tail = f"{tail}\nЗауваження: " + "; ".join(measure.warnings)
                data.append([
                    paragraph(measure.sequence_number if measure.sequence_number is not None else "—", center_style),
                    measure_cell(measure, section.number),
                    paragraph(measure.factual_date.strftime("%d.%m.%Y") if measure.factual_date else "—", center_style),
                    paragraph(measure.execution_status),
                    paragraph(tail),
                ])
                fill = status_fill.get(measure.execution_status)
                if fill is not None:
                    r = len(data) - 1
                    styles.append(("BACKGROUND", (3, r), (3, r), fill))
        if len(data) == 1:
            data.append([paragraph("—", center_style), paragraph("Заходів немає"),
                         paragraph("—", center_style), paragraph("—"), paragraph("—")])
        table = LongTable(
            data, colWidths=col_widths, repeatRows=1, hAlign="LEFT",
            splitByRow=1, splitInRow=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), pale),
            ("GRID", (0, 0), (-1, -1), .35, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            *styles,
        ]))
        flow.extend([table, Spacer(1, 9)])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(30, 30, page[0] - 30, 30)
        canvas.setFont("AnticorPDFRegular", 8)
        canvas.setFillColor(muted)
        canvas.drawString(30, 18, f"Anticor_monitor  ·  {snapshot.period}  ·  Звіт №{report_id}")
        canvas.drawRightString(page[0] - 30, 18, f"Сторінка {doc.page}")
        canvas.restoreState()

    try:
        document.build(flow, onFirstPage=footer, onLaterPages=footer)
    except Exception as exc:
        raise PDFExportError(f"Не вдалося сформувати PDF звіту: {exc}") from exc
    return buffer.getvalue()
