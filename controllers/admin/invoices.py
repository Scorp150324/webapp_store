from io import BytesIO
from pathlib import Path

from flask import abort, send_file
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database import engine, text


def _load_invoice(order_id):
    with engine.connect() as connection:
        order = connection.execute(
            text(
                "SELECT o.OrderID, o.OrderCode, o.OrderDate, o.SubTotal, "
                "o.DiscountAmount, o.TotalAmount, o.OrderStatus, o.Notes, "
                "c.FullName AS CustomerName, c.Phone AS CustomerPhone, c.Email AS CustomerEmail, "
                "u.FullName AS EmployeeName "
                "FROM Orders AS o "
                "LEFT JOIN Customers AS c ON c.CustomerID=o.CustomerID "
                "LEFT JOIN Users AS u ON u.UserID=o.EmployeeID "
                "WHERE o.OrderID=:order_id "
                "AND COALESCE(o.OrderStatus, '') NOT LIKE 'DELETED%'"
            ),
            {"order_id": order_id},
        ).mappings().first()
        if order is None:
            return None

        details = connection.execute(
            text(
                "SELECT od.OrderDetailID, p.SKU, p.ProductName, od.Quantity, "
                "od.UnitPrice, od.TotalPrice "
                "FROM Order_Details AS od "
                "JOIN Products AS p ON p.ProductID=od.ProductID "
                "WHERE od.OrderID=:order_id "
                "ORDER BY od.OrderDetailID"
            ),
            {"order_id": order_id},
        ).mappings().all()

        serials = connection.execute(
            text(
                "SELECT ps.OrderDetailID, ps.SerialNumber "
                "FROM Product_Serials AS ps "
                "JOIN Order_Details AS od ON od.OrderDetailID=ps.OrderDetailID "
                "WHERE od.OrderID=:order_id "
                "ORDER BY ps.SerialID"
            ),
            {"order_id": order_id},
        ).mappings().all()

        payment = connection.execute(
            text(
                "SELECT PaymentMethod, PaymentStatus, PaidAmount, Amount "
                "FROM Payments WHERE OrderID=:order_id "
                "ORDER BY PaymentID DESC"
            ),
            {"order_id": order_id},
        ).mappings().first()

    serial_by_detail = {}
    for row in serials:
        serial_by_detail.setdefault(row["OrderDetailID"], []).append(row["SerialNumber"])
    return order, details, serial_by_detail, payment


def _money(value):
    return f"{float(value or 0):,.0f} VND"


def _safe_filename(order_code):
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in order_code)


def export_invoice_excel(order_id):
    invoice = _load_invoice(order_id)
    if invoice is None:
        abort(404)
    order, details, serial_by_detail, payment = invoice

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Hoa don"
    sheet["A1"] = "HÓA ĐƠN BÁN HÀNG"
    sheet["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    sheet["A1"].fill = PatternFill("solid", fgColor="1E3A8A")
    sheet.merge_cells("A1:G1")
    sheet["A2"] = "PHÚC THỊNH ICT"
    sheet.merge_cells("A2:G2")

    info = [
        ("Mã hóa đơn", order["OrderCode"]),
        ("Ngày lập", str(order["OrderDate"])),
        ("Khách hàng", order["CustomerName"] or "Khách lẻ"),
        ("Điện thoại", order["CustomerPhone"] or ""),
        ("Email", order["CustomerEmail"] or ""),
        ("Nhân viên", order["EmployeeName"] or ""),
        ("Trạng thái", order["OrderStatus"]),
        ("Thanh toán", f"{payment['PaymentMethod']} - {payment['PaymentStatus']}" if payment else ""),
    ]
    row = 4
    for label, value in info:
        sheet.cell(row, 1, label).font = Font(bold=True)
        sheet.cell(row, 2, value)
        row += 1

    headers = ["STT", "Mã SKU", "Sản phẩm", "Số lượng", "Đơn giá", "Thành tiền", "Serial"]
    header_row = row + 1
    for column, header in enumerate(headers, 1):
        cell = sheet.cell(header_row, column, header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")
        cell.alignment = Alignment(horizontal="center")

    for index, detail in enumerate(details, 1):
        current = header_row + index
        serials = "\n".join(serial_by_detail.get(detail["OrderDetailID"], []))
        values = [
            index,
            detail["SKU"],
            detail["ProductName"],
            detail["Quantity"],
            float(detail["UnitPrice"]),
            float(detail["TotalPrice"]),
            serials,
        ]
        for column, value in enumerate(values, 1):
            sheet.cell(current, column, value)
        sheet.cell(current, 5).number_format = '#,##0 "VND"'
        sheet.cell(current, 6).number_format = '#,##0 "VND"'

    summary_row = header_row + len(details) + 2
    sheet.cell(summary_row, 5, "Tạm tính").font = Font(bold=True)
    sheet.cell(summary_row, 6, float(order["SubTotal"])).number_format = '#,##0 "VND"'
    sheet.cell(summary_row + 1, 5, "Giảm giá").font = Font(bold=True)
    sheet.cell(summary_row + 1, 6, float(order["DiscountAmount"])).number_format = '#,##0 "VND"'
    sheet.cell(summary_row + 2, 5, "TỔNG CỘNG").font = Font(bold=True)
    sheet.cell(summary_row + 2, 6, float(order["TotalAmount"])).number_format = '#,##0 "VND"'
    sheet.cell(summary_row + 2, 5).fill = PatternFill("solid", fgColor="DBEAFE")
    sheet.cell(summary_row + 2, 6).fill = PatternFill("solid", fgColor="DBEAFE")

    sheet.cell(summary_row + 4, 1, "Ghi chú")
    sheet.cell(summary_row + 4, 2, order["Notes"] or "")

    widths = [8, 18, 38, 12, 16, 18, 28]
    for column, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.freeze_panes = f"A{header_row + 1}"
    sheet.auto_filter.ref = f"A{header_row}:G{header_row + len(details)}"

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    filename = f"Hoa_don_{_safe_filename(order['OrderCode'])}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _register_vietnamese_font():
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    bold_candidates = [
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            pdfmetrics.registerFont(TTFont("InvoiceFont", candidate))
            break
    else:
        return "Helvetica", "Helvetica-Bold"

    for candidate in bold_candidates:
        if Path(candidate).is_file():
            pdfmetrics.registerFont(TTFont("InvoiceFont-Bold", candidate))
            return "InvoiceFont", "InvoiceFont-Bold"
    return "InvoiceFont", "InvoiceFont"


def export_invoice_pdf(order_id):
    invoice = _load_invoice(order_id)
    if invoice is None:
        abort(404)
    order, details, serial_by_detail, payment = invoice

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Hoa don {order['OrderCode']}",
    )
    regular_font, bold_font = _register_vietnamese_font()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=18,
        textColor=colors.HexColor("#1e3a8a"),
        alignment=TA_RIGHT,
    )
    normal = ParagraphStyle(
        "InvoiceNormal",
        parent=styles["BodyText"],
        fontName=regular_font,
        fontSize=9,
        leading=12,
    )
    small_bold = ParagraphStyle(
        "InvoiceSmallBold",
        parent=normal,
        fontName=bold_font,
        fontSize=9,
    )

    story = [
        Paragraph("PHÚC THỊNH ICT", title),
        Paragraph("HÓA ĐƠN BÁN HÀNG", title),
        Spacer(1, 4 * mm),
    ]

    info_data = [
        [Paragraph("<b>Mã hóa đơn:</b>", normal), Paragraph(str(order["OrderCode"]), normal)],
        [Paragraph("<b>Ngày lập:</b>", normal), Paragraph(str(order["OrderDate"]), normal)],
        [Paragraph("<b>Khách hàng:</b>", normal), Paragraph(order["CustomerName"] or "Khách lẻ", normal)],
        [Paragraph("<b>Điện thoại:</b>", normal), Paragraph(order["CustomerPhone"] or "", normal)],
        [Paragraph("<b>Nhân viên:</b>", normal), Paragraph(order["EmployeeName"] or "", normal)],
        [Paragraph("<b>Thanh toán:</b>", normal), Paragraph(
            f"{payment['PaymentMethod']} - {payment['PaymentStatus']}" if payment else "",
            normal,
        )],
    ]
    info_table = Table(info_data, colWidths=[35 * mm, 145 * mm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), regular_font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([info_table, Spacer(1, 5 * mm)])

    table_data = [[
        "STT", "Sản phẩm", "Serial", "SL", "Đơn giá", "Thành tiền"
    ]]
    for index, detail in enumerate(details, 1):
        serials = ", ".join(serial_by_detail.get(detail["OrderDetailID"], [])) or "-"
        table_data.append([
            str(index),
            f"{detail['ProductName']}\nSKU: {detail['SKU']}",
            serials,
            str(detail["Quantity"]),
            _money(detail["UnitPrice"]),
            _money(detail["TotalPrice"]),
        ])

    invoice_table = Table(
        table_data,
        colWidths=[10 * mm, 68 * mm, 38 * mm, 10 * mm, 27 * mm, 27 * mm],
        repeatRows=1,
    )
    invoice_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563eb")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("FONTNAME", (0, 1), (-1, -1), regular_font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#94a3b8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([invoice_table, Spacer(1, 5 * mm)])

    summary = Table([
        ["Tạm tính", _money(order["SubTotal"])],
        ["Giảm giá", _money(order["DiscountAmount"])],
        ["TỔNG CỘNG", _money(order["TotalAmount"])],
    ], colWidths=[40 * mm, 40 * mm], hAlign="RIGHT")
    summary.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), regular_font),
        ("FONTNAME", (0, 2), (-1, 2), bold_font),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("LINEABOVE", (0, 2), (-1, 2), 1, colors.HexColor("#1e3a8a")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([summary, Spacer(1, 6 * mm)])
    if order["Notes"]:
        story.append(Paragraph(f"<b>Ghi chú:</b> {order['Notes']}", normal))

    document.build(story)
    output.seek(0)
    filename = f"Hoa_don_{_safe_filename(order['OrderCode'])}.pdf"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf",
    )
