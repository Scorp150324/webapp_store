from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from flask import request, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from controllers.admin.analytics import get_period, load_analytics
from controllers.admin.invoices import _register_vietnamese_font
from database import engine

PERIOD_LABELS = {"day": "Theo ngày", "month": "Theo tháng", "year": "Theo năm"}


def _load_statistics():
    period_key = request.args.get("period", "day")
    selected_date = request.args.get("date", date.today().isoformat())
    period = get_period(period_key, selected_date)
    with engine.connect() as connection:
        analytics = load_analytics(connection, period)
    return period_key, period, analytics


def _build_excel(period_key, period, analytics):
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Tong quan"
    summary["A1"] = "BÁO CÁO THỐNG KÊ DOANH THU"
    summary["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    summary["A1"].fill = PatternFill("solid", fgColor="1E3A8A")
    summary.merge_cells("A1:B1")
    summary["A2"] = PERIOD_LABELS[period_key]
    summary["B2"] = period["period_label"]
    summary["A4"] = "Tổng doanh thu"
    summary["B4"] = float(analytics["period_sales"])
    summary["B4"].number_format = '#,##0 "VND"'
    summary["A5"] = "Số đơn hàng hợp lệ"
    summary["B5"] = analytics["period_order_count"]
    summary["A6"] = "Giá trị trung bình/đơn"
    summary["B6"] = (
        float(analytics["period_sales"]) / analytics["period_order_count"]
        if analytics["period_order_count"]
        else 0
    )
    summary["B6"].number_format = '#,##0 "VND"'
    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 24

    revenue = workbook.create_sheet("Doanh thu")
    revenue.append(["Thời gian", "Doanh thu (VND)"])
    for cell in revenue[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")
    for label, amount in zip(
        analytics["sales_chart"]["labels"],
        analytics["sales_chart"]["values"],
    ):
        revenue.append([label, float(amount)])
        revenue.cell(revenue.max_row, 2).number_format = '#,##0 "VND"'
    revenue.freeze_panes = "A2"
    revenue.auto_filter.ref = revenue.dimensions
    revenue.column_dimensions["A"].width = 20
    revenue.column_dimensions["B"].width = 24

    categories = workbook.create_sheet("Danh muc")
    categories.append(["Danh mục", "Doanh số (VND)"])
    for cell in categories[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")
    for category in analytics["category_chart"]:
        categories.append([category["label"], float(category["value"])])
        categories.cell(categories.max_row, 2).number_format = '#,##0 "VND"'
    categories.freeze_panes = "A2"
    categories.auto_filter.ref = categories.dimensions
    categories.column_dimensions["A"].width = 38
    categories.column_dimensions["B"].width = 24

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                cell.alignment = Alignment(vertical="center")

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return output


def _build_pdf(period_key, period, analytics):
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="Báo cáo thống kê doanh thu",
    )
    regular_font, bold_font = _register_vietnamese_font()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "StatisticsTitle",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=17,
        textColor=colors.HexColor("#1e3a8a"),
    )
    normal_style = ParagraphStyle(
        "StatisticsBody",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=9,
        leading=12,
    )
    header_style = ParagraphStyle(
        "StatisticsHeader",
        parent=normal_style,
        fontName=bold_font,
        textColor=colors.white,
    )
    right_style = ParagraphStyle(
        "StatisticsRight",
        parent=normal_style,
        alignment=TA_RIGHT,
    )

    revenue_total = float(analytics["period_sales"])
    order_count = int(analytics["period_order_count"])
    summary_table = Table(
        [
            ["Khoảng thống kê", PERIOD_LABELS[period_key]],
            ["Kỳ", period["period_label"]],
            ["Tổng doanh thu", f"{revenue_total:,.0f} VND"],
            ["Số đơn hàng hợp lệ", str(order_count)],
            [
                "Giá trị trung bình/đơn",
                f"{(revenue_total / order_count if order_count else 0):,.0f} VND",
            ],
        ],
        colWidths=[60 * mm, 110 * mm],
    )
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), regular_font),
                ("FONTNAME", (0, 2), (0, 2), bold_font),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#dbeafe")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story = [
        Paragraph("BÁO CÁO THỐNG KÊ DOANH THU", title_style),
        Spacer(1, 3 * mm),
        summary_table,
        Spacer(1, 7 * mm),
        Paragraph("Doanh thu theo thời gian", ParagraphStyle(
            "RevenueHeading", parent=normal_style, fontName=bold_font, fontSize=12
        )),
        Spacer(1, 2 * mm),
    ]
    revenue_data = [
        [
            Paragraph("Thời gian", header_style),
            Paragraph("Doanh thu (VND)", ParagraphStyle(
                "StatisticsHeaderRight", parent=header_style, alignment=TA_RIGHT
            )),
        ]
    ]
    for label, amount in zip(
        analytics["sales_chart"]["labels"],
        analytics["sales_chart"]["values"],
    ):
        revenue_data.append(
            [
                Paragraph(escape(str(label)), normal_style),
                Paragraph(f"{float(amount):,.0f}", right_style),
            ]
        )
    revenue_table = Table(
        revenue_data,
        colWidths=[80 * mm, 90 * mm],
        repeatRows=1,
    )
    revenue_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), regular_font),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend(
        [
            revenue_table,
            Spacer(1, 7 * mm),
            Paragraph("Doanh số theo danh mục", ParagraphStyle(
                "CategoryHeading", parent=normal_style, fontName=bold_font, fontSize=12
            )),
            Spacer(1, 2 * mm),
        ]
    )

    category_data = [
        [
            Paragraph("Danh mục", header_style),
            Paragraph("Doanh số (VND)", ParagraphStyle(
                "CategoryHeaderRight", parent=header_style, alignment=TA_RIGHT
            )),
        ]
    ]
    for category in analytics["category_chart"]:
        category_data.append(
            [
                Paragraph(escape(str(category["label"])), normal_style),
                Paragraph(f"{float(category['value']):,.0f}", right_style),
            ]
        )
    category_table = Table(
        category_data,
        colWidths=[80 * mm, 90 * mm],
        repeatRows=1,
    )
    category_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), regular_font),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(category_table)
    document.build(story)
    output.seek(0)
    return output


def _filename(period_key, period, extension):
    date_part = period["selected_date"].isoformat()
    return f"Thong_ke_{period_key}_{date_part}.{extension}"


def export_statistics_excel():
    period_key, period, analytics = _load_statistics()
    return send_file(
        _build_excel(period_key, period, analytics),
        as_attachment=True,
        download_name=_filename(period_key, period, "xlsx"),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def export_statistics_pdf():
    period_key, period, analytics = _load_statistics()
    return send_file(
        _build_pdf(period_key, period, analytics),
        as_attachment=True,
        download_name=_filename(period_key, period, "pdf"),
        mimetype="application/pdf",
    )
