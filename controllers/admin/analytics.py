from calendar import monthrange
from datetime import date, timedelta

from flask import abort
from sqlalchemy import text

VALID_ORDER_STATUSES = ("PAID", "COMPLETED", "SHIPPED")


def get_period(period, selected_date_value):
    if period not in {"day", "month", "year"}:
        abort(400, description="Khoảng thống kê không hợp lệ.")
    try:
        selected_date = date.fromisoformat(selected_date_value)
    except ValueError:
        abort(400, description="Ngày thống kê không hợp lệ.")
    if selected_date.year == 9999:
        abort(400, description="Năm thống kê không hợp lệ.")

    if period == "day":
        range_start = selected_date
        range_end = range_start + timedelta(days=1)
        period_label = selected_date.strftime("%d/%m/%Y")
        bucket_expression = "HOUR(OrderDate)"
        bucket_numbers = range(24)
        chart_labels = [f"{hour:02d}:00" for hour in bucket_numbers]
    elif period == "month":
        range_start = selected_date.replace(day=1)
        range_end = (
            range_start.replace(year=range_start.year + 1, month=1)
            if range_start.month == 12
            else range_start.replace(month=range_start.month + 1)
        )
        period_label = selected_date.strftime("%m/%Y")
        bucket_expression = "DAYOFMONTH(OrderDate)"
        bucket_numbers = range(1, monthrange(range_start.year, range_start.month)[1] + 1)
        chart_labels = [str(day) for day in bucket_numbers]
    else:
        range_start = selected_date.replace(month=1, day=1)
        range_end = range_start.replace(year=range_start.year + 1)
        period_label = str(selected_date.year)
        bucket_expression = "MONTH(OrderDate)"
        bucket_numbers = range(1, 13)
        chart_labels = [f"{month:02d}" for month in bucket_numbers]

    return {
        "selected_date": selected_date,
        "range_start": range_start,
        "range_end": range_end,
        "period_label": period_label,
        "bucket_expression": bucket_expression,
        "bucket_numbers": bucket_numbers,
        "chart_labels": chart_labels,
    }


def load_analytics(connection, period):
    parameters = {
        "range_start": period["range_start"],
        "range_end": period["range_end"],
    }
    revenue_rows = connection.execute(
        text(
            "SELECT "
            f"{period['bucket_expression']} AS period_bucket, "
            "COALESCE(SUM(TotalAmount), 0) AS revenue, COUNT(*) AS order_count "
            "FROM Orders "
            "WHERE OrderStatus IN ('PAID', 'COMPLETED', 'SHIPPED') "
            "AND OrderDate >= :range_start AND OrderDate < :range_end "
            "GROUP BY period_bucket ORDER BY period_bucket"
        ),
        parameters,
    ).mappings().all()
    category_rows = connection.execute(
        text(
            "SELECT COALESCE(c.CategoryName, 'Chưa phân loại') AS category_name, "
            "COALESCE(SUM(od.TotalPrice), 0) AS sales_amount "
            "FROM Order_Details AS od "
            "JOIN Orders AS o ON o.OrderID = od.OrderID "
            "LEFT JOIN Products AS p ON p.ProductID = od.ProductID "
            "LEFT JOIN Categories AS c ON c.CategoryID = p.CategoryID "
            "WHERE o.OrderStatus IN ('PAID', 'COMPLETED', 'SHIPPED') "
            "AND o.OrderDate >= :range_start AND o.OrderDate < :range_end "
            "GROUP BY c.CategoryID, c.CategoryName "
            "ORDER BY sales_amount DESC, category_name"
        ),
        parameters,
    ).mappings().all()
    revenue_by_bucket = {int(row["period_bucket"]): row for row in revenue_rows}
    return {
        "sales_chart": {
            "labels": period["chart_labels"],
            "values": [
                float(revenue_by_bucket[bucket]["revenue"] or 0)
                if bucket in revenue_by_bucket
                else 0
                for bucket in period["bucket_numbers"]
            ],
        },
        "period_sales": sum((row["revenue"] or 0 for row in revenue_rows), start=0),
        "period_order_count": sum(int(row["order_count"]) for row in revenue_rows),
        "category_chart": [
            {"label": row["category_name"], "value": float(row["sales_amount"] or 0)}
            for row in category_rows
        ],
    }
