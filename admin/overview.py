import logging
import secrets
from datetime import date

from flask import abort, render_template, request, session
from sqlalchemy import text

from admin.analytics import get_period, load_analytics
from database import engine

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
                    "(SELECT COUNT(*) FROM Orders "
                    "WHERE OrderDate >= CURDATE()) AS orders_today"
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
            customers = connection.execute(
                text(
                    "SELECT CustomerID, Username, FullName, Phone, Email, "
                    "TotalSpent, RewardPoints "
                    "FROM Customers WHERE IsDeleted = 0 "
                    "ORDER BY CustomerID DESC LIMIT 100"
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
                    "SELECT i.InboundID, i.ImportDate, i.TotalAmount, i.Status, "
                    "s.SupplierName, u.FullName AS EmployeeName "
                    "FROM Inbound_Notes AS i "
                    "LEFT JOIN Suppliers AS s ON s.SupplierID = i.SupplierID "
                    "LEFT JOIN Users AS u ON u.UserID = i.CreatedBy "
                    "ORDER BY i.ImportDate DESC LIMIT 50"
                )
            ).mappings().all()
            orders = connection.execute(
                text(
                    "SELECT o.OrderID, o.OrderCode, o.OrderDate, o.TotalAmount, "
                    "o.OrderStatus, c.FullName AS CustomerName, u.FullName AS EmployeeName "
                    "FROM Orders AS o "
                    "LEFT JOIN Customers AS c ON c.CustomerID = o.CustomerID "
                    "LEFT JOIN Users AS u ON u.UserID = o.EmployeeID "
                    "ORDER BY o.OrderDate DESC LIMIT 50"
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
            analytics = load_analytics(connection, selected_period)
    except Exception:
        logger.exception("Không thể tải dashboard quản lý")
        abort(503, description="Không thể tải dữ liệu quản lý. Kiểm tra schema cơ sở dữ liệu.")

    return render_template(
        "dashboard.html",
        csrf_token=csrf_token,
        period=request.args.get("period", "day"),
        selected_date=selected_period["selected_date"].isoformat(),
        period_label=selected_period["period_label"],
        **analytics,
        stats=stats,
        roles=roles,
        employees=employees,
        customers=customers,
        products=products,
        hidden_products=hidden_products,
        categories=categories,
        suppliers=suppliers,
        inbound_notes=inbound_notes,
        orders=orders,
        login_logs=login_logs,
    )
