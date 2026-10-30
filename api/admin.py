from flask import abort, jsonify, session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api import api_bp
from database import engine

MANAGER_ROLE_IDS = {1, 5}


@api_bp.get("/admin/dashboard")
def dashboard_summary():
    if (
        session.get("user_type") != "staff"
        or session.get("role_id") not in MANAGER_ROLE_IDS
    ):
        abort(403, description="Bạn không có quyền xem dữ liệu quản trị.")

    try:
        with engine.connect() as connection:
            stats = connection.execute(
                text(
                    "SELECT "
                    "(SELECT COUNT(*) FROM Users WHERE IsDeleted = 0) AS employee_count, "
                    "(SELECT COUNT(*) FROM Customers WHERE IsDeleted = 0) AS customer_count, "
                    "(SELECT COUNT(*) FROM Products WHERE IsDeleted = 0) AS product_count, "
                    "(SELECT COALESCE(SUM(StockQuantity), 0) FROM Products "
                    "WHERE IsDeleted = 0) AS stock_count, "
                    "(SELECT COALESCE(SUM(TotalAmount), 0) FROM Orders "
                    "WHERE OrderStatus IN ('PAID', 'COMPLETED', 'SHIPPED')) AS sales_total, "
                    "(SELECT COUNT(*) FROM Orders WHERE OrderDate >= CURDATE()) "
                    "AS orders_today"
                )
            ).mappings().one()
    except SQLAlchemyError:
        abort(503, description="Không thể tải số liệu quản trị lúc này.")

    return jsonify(
        data={
            "employee_count": stats["employee_count"],
            "customer_count": stats["customer_count"],
            "product_count": stats["product_count"],
            "stock_count": stats["stock_count"],
            "sales_total": float(stats["sales_total"] or 0),
            "orders_today": stats["orders_today"],
        }
    )
