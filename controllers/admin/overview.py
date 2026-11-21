import logging
import secrets
from datetime import date

from flask import abort, jsonify, render_template, request, session
from controllers.admin.analytics import get_period, load_analytics
from database import engine, text

logger = logging.getLogger(__name__)


def home():
    csrf_token = session.setdefault("dashboard_csrf_token", secrets.token_urlsafe(32))
    selected_period = get_period(
        request.args.get("period", "day"),
        request.args.get("date", date.today().isoformat()),
    )
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
                    "(SELECT COUNT(*) FROM Orders WHERE OrderDate >= CURRENT_DATE "
                    "AND COALESCE(OrderStatus, '') NOT LIKE 'DELETED%') AS orders_today"
                )
            ).mappings().one()
            roles = connection.execute(
                text("SELECT RoleID, RoleName FROM Roles ORDER BY RoleID")
            ).mappings().all()
            employees = connection.execute(
                text(
                    "SELECT u.UserID, u.Username, u.FullName, u.Email, u.Phone, "
                    "u.RoleID, r.RoleName "
                    "FROM Users AS u LEFT JOIN Roles AS r ON r.RoleID = u.RoleID "
                    "WHERE u.IsDeleted = 0 ORDER BY u.UserID DESC LIMIT 100"
                )
            ).mappings().all()
            hidden_employees = []
            if session.get("role_id") == 1:
                hidden_employees = connection.execute(
                    text(
                        "SELECT u.UserID, u.Username, u.FullName, u.Email, u.Phone, "
                        "u.DeletedAt, r.RoleName "
                        "FROM Users AS u LEFT JOIN Roles AS r ON r.RoleID = u.RoleID "
                        "WHERE u.IsDeleted = 1 "
                        "ORDER BY u.DeletedAt DESC, u.UserID DESC LIMIT 100"
                    )
                ).mappings().all()
            customers = connection.execute(
                text(
                    "SELECT CustomerID, Username, FullName, Phone, Email, "
                    "TotalSpent, RewardPoints "
                    "FROM Customers WHERE IsDeleted = 0 "
                    "ORDER BY CustomerID DESC LIMIT 100"
                )
            ).mappings().all()
            hidden_customers = []
            if session.get("role_id") == 1:
                hidden_customers = connection.execute(
                    text(
                        "SELECT CustomerID, Username, FullName, Phone, Email, DeletedAt "
                        "FROM Customers WHERE IsDeleted = 1 "
                        "ORDER BY DeletedAt DESC, CustomerID DESC LIMIT 100"
                    )
                ).mappings().all()
            products = connection.execute(
                text(
                    "SELECT p.ProductID, p.SKU, p.Barcode, p.ProductName, "
                    "p.CategoryID, p.SupplierID, p.MainImage, p.Specifications, "
                    "p.CostPrice, p.SellingPrice, p.StockQuantity, p.WarrantyMonths, "
                    "p.IsHasSerial, c.CategoryName, s.SupplierName "
                    "FROM Products AS p "
                    "LEFT JOIN Categories AS c ON c.CategoryID = p.CategoryID "
                    "LEFT JOIN Suppliers AS s ON s.SupplierID = p.SupplierID "
                    "WHERE p.IsDeleted = 0 ORDER BY p.ProductID DESC LIMIT 100"
                )
            ).mappings().all()
            hidden_products = connection.execute(
                text(
                    "SELECT p.ProductID, p.SKU, p.ProductName, p.MainImage, "
                    "p.StockQuantity, p.SellingPrice, p.DeletedAt, "
                    "c.CategoryName, s.SupplierName "
                    "FROM Products AS p "
                    "LEFT JOIN Categories AS c ON c.CategoryID = p.CategoryID "
                    "LEFT JOIN Suppliers AS s ON s.SupplierID = p.SupplierID "
                    "WHERE p.IsDeleted = 1 ORDER BY p.DeletedAt DESC, p.ProductID DESC "
                    "LIMIT 100"
                )
            ).mappings().all()
            categories = connection.execute(
                text("SELECT CategoryID, CategoryName FROM Categories ORDER BY CategoryName")
            ).mappings().all()
            suppliers = connection.execute(
                text("SELECT SupplierID, SupplierName FROM Suppliers ORDER BY SupplierName")
            ).mappings().all()
            inbound_notes = connection.execute(
                text(
                    "SELECT i.InboundID, i.SupplierID, i.ImportDate, i.TotalAmount, "
                    "i.Status, i.Notes, "
                    "s.SupplierName, u.FullName AS EmployeeName "
                    "FROM Inbound_Notes AS i "
                    "LEFT JOIN Suppliers AS s ON s.SupplierID = i.SupplierID "
                    "LEFT JOIN Users AS u ON u.UserID = i.CreatedBy "
                    "WHERE COALESCE(i.Status, '') NOT LIKE 'DELETED%' "
                    "ORDER BY i.ImportDate DESC LIMIT 50"
                )
            ).mappings().all()
            hidden_inbound_notes = connection.execute(
                text(
                    "SELECT i.InboundID, i.SupplierID, i.ImportDate, i.TotalAmount, "
                    "i.Status, i.Notes, s.SupplierName "
                    "FROM Inbound_Notes AS i "
                    "LEFT JOIN Suppliers AS s ON s.SupplierID = i.SupplierID "
                    "WHERE COALESCE(i.Status, '') LIKE 'DELETED%' "
                    "ORDER BY i.ImportDate DESC, i.InboundID DESC LIMIT 100"
                )
            ).mappings().all()
            orders = connection.execute(
                text(
                    "SELECT o.OrderID, o.OrderCode, o.OrderDate, o.TotalAmount, "
                    "o.OrderStatus, o.Notes, c.FullName AS CustomerName, "
                    "u.FullName AS EmployeeName "
                    "FROM Orders AS o "
                    "LEFT JOIN Customers AS c ON c.CustomerID = o.CustomerID "
                    "LEFT JOIN Users AS u ON u.UserID = o.EmployeeID "
                    "WHERE COALESCE(o.OrderStatus, '') NOT LIKE 'DELETED%' "
                    "ORDER BY o.OrderDate DESC LIMIT 50"
                )
            ).mappings().all()
            hidden_orders = connection.execute(
                text(
                    "SELECT o.OrderID, o.OrderCode, o.OrderDate, o.TotalAmount, "
                    "o.OrderStatus, c.FullName AS CustomerName "
                    "FROM Orders AS o "
                    "LEFT JOIN Customers AS c ON c.CustomerID = o.CustomerID "
                    "WHERE COALESCE(o.OrderStatus, '') LIKE 'DELETED%' "
                    "ORDER BY o.OrderDate DESC, o.OrderID DESC LIMIT 100"
                )
            ).mappings().all()
            login_logs = connection.execute(
                text(
                    "SELECT l.LoginLogID, l.LoggedAt, l.IPAddress, l.UserAgent, "
                    "c.FullName, c.Phone, c.Email "
                    "FROM Customer_Login_Logs AS l "
                    "JOIN Customers AS c ON c.CustomerID = l.CustomerID "
                    "ORDER BY l.LoggedAt DESC LIMIT 100"
                )
            ).mappings().all()
    except Exception:
        logger.exception("Không thể tải dashboard quản lý")
        abort(503, description="Không thể tải dữ liệu quản lý. Kiểm tra schema cơ sở dữ liệu.")

    return render_template(
        "dashboard.html",
        csrf_token=csrf_token,
        period=request.args.get("period", "day"),
        selected_date=selected_period["selected_date"].isoformat(),
        period_label=selected_period["period_label"],
        stats=stats,
        roles=roles,
        employees=employees,
        hidden_employees=hidden_employees,
        customers=customers,
        hidden_customers=hidden_customers,
        products=products,
        hidden_products=hidden_products,
        categories=categories,
        suppliers=suppliers,
        inbound_notes=inbound_notes,
        hidden_inbound_notes=hidden_inbound_notes,
        orders=orders,
        hidden_orders=hidden_orders,
        login_logs=login_logs,
    )


def analytics_data():
    period = get_period(
        request.args.get("period", "day"),
        request.args.get("date", date.today().isoformat()),
    )
    try:
        with engine.connect() as connection:
            analytics = load_analytics(connection, period)
    except Exception:
        logger.exception("Unable to load dashboard analytics")
        abort(503, description="Không thể tải dữ liệu thống kê lúc này.")

    return jsonify(
        period=period["period_label"],
        selected_date=period["selected_date"].isoformat(),
        period_sales=float(analytics["period_sales"] or 0),
        period_order_count=analytics["period_order_count"],
        sales_chart=analytics["sales_chart"],
        category_chart=analytics["category_chart"],
    )
