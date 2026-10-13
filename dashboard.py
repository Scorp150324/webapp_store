import hmac
import logging
import secrets
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

import bcrypt
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from database import engine

dashboard_bp = Blueprint("dashboard", __name__)
logger = logging.getLogger(__name__)
MANAGER_ROLE_IDS = {1, 5}


class DashboardInputError(ValueError):
    pass


def manager_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if (
            session.get("user_type") != "staff"
            or session.get("role_id") not in MANAGER_ROLE_IDS
        ):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def form_value(name, *, required=False, maximum=None):
    value = request.form.get(name, "").strip()
    if required and not value:
        raise DashboardInputError(f"Trường {name} là bắt buộc.")
    if maximum is not None and len(value) > maximum:
        raise DashboardInputError(f"Trường {name} không được dài quá {maximum} ký tự.")
    return value


def form_int(name, *, minimum=None, optional=False):
    value = form_value(name)
    if not value and optional:
        return None
    try:
        result = int(value)
    except ValueError as error:
        raise DashboardInputError(f"Giá trị {name} không hợp lệ.") from error
    if minimum is not None and result < minimum:
        raise DashboardInputError(f"Giá trị {name} phải lớn hơn hoặc bằng {minimum}.")
    return result


def form_decimal(name, *, minimum=Decimal("0")):
    try:
        value = Decimal(form_value(name, required=True))
    except InvalidOperation as error:
        raise DashboardInputError(f"Giá trị {name} không hợp lệ.") from error
    if not value.is_finite() or value < minimum:
        raise DashboardInputError(f"Giá trị {name} không hợp lệ.")
    return value


def check_csrf_token():
    expected = session.get("dashboard_csrf_token", "")
    supplied = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        abort(400, description="Phiên biểu mẫu hết hạn. Hãy tải lại trang và thử lại.")


@dashboard_bp.before_request
def guard_dashboard():
    if (
        session.get("user_type") != "staff"
        or session.get("role_id") not in MANAGER_ROLE_IDS
    ):
        abort(403)
    if request.method == "POST":
        check_csrf_token()


@dashboard_bp.route("/dashboard")
@manager_required
def home():
    csrf_token = session.setdefault("dashboard_csrf_token", secrets.token_urlsafe(32))
    period = request.args.get("period", "day")
    if period not in {"day", "month", "year"}:
        abort(400, description="Khoảng thống kê không hợp lệ.")
    selected_date_value = request.args.get("date", date.today().isoformat())
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
                    "SELECT CustomerID, FullName, Phone, Email, TotalSpent, RewardPoints "
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
            revenue_rows = connection.execute(
                text(
                    "SELECT "
                    f"{bucket_expression} AS period_bucket, "
                    "COALESCE(SUM(TotalAmount), 0) AS revenue, COUNT(*) AS order_count "
                    "FROM Orders "
                    "WHERE OrderStatus IN ('PAID', 'COMPLETED', 'SHIPPED') "
                    "AND OrderDate >= :range_start AND OrderDate < :range_end "
                    "GROUP BY period_bucket ORDER BY period_bucket"
                ),
                {"range_start": range_start, "range_end": range_end},
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
                {"range_start": range_start, "range_end": range_end},
            ).mappings().all()
    except Exception:
        logger.exception("Không thể tải dashboard quản lý")
        abort(503, description="Không thể tải dữ liệu quản lý. Kiểm tra schema cơ sở dữ liệu.")

    revenue_by_bucket = {
        int(row["period_bucket"]): row for row in revenue_rows
    }
    sales_chart = {
        "labels": chart_labels,
        "values": [
            float(revenue_by_bucket[bucket]["revenue"] or 0)
            if bucket in revenue_by_bucket
            else 0
            for bucket in bucket_numbers
        ],
    }
    period_sales = sum(
        (row["revenue"] or 0 for row in revenue_rows),
        start=0,
    )
    period_order_count = sum(int(row["order_count"]) for row in revenue_rows)
    category_chart = [
        {
            "label": row["category_name"],
            "value": float(row["sales_amount"] or 0),
        }
        for row in category_rows
    ]

    return render_template(
        "dashboard.html",
        csrf_token=csrf_token,
        period=period,
        selected_date=selected_date.isoformat(),
        period_label=period_label,
        period_sales=period_sales,
        period_order_count=period_order_count,
        sales_chart=sales_chart,
        category_chart=category_chart,
        stats=stats,
        roles=roles,
        employees=employees,
        customers=customers,
        products=products,
        categories=categories,
        suppliers=suppliers,
        inbound_notes=inbound_notes,
        orders=orders,
        login_logs=login_logs,
    )


@dashboard_bp.route("/dashboard/action/<action>", methods=["POST"])
@manager_required
def action(action):
    if action not in {
        "employee-create",
        "employee-update",
        "employee-delete",
        "customer-create",
        "customer-update",
        "customer-delete",
        "product-create",
        "product-update",
        "product-delete",
        "inbound-create",
        "outbound-create",
    }:
        abort(404)
    if action.startswith("employee-") and session.get("role_id") != 1:
        abort(403)

    try:
        with engine.begin() as connection:
            if action == "employee-create":
                full_name = form_value("full_name", required=True, maximum=100)
                username = form_value("username", required=True, maximum=50)
                email = form_value("email", maximum=100) or None
                phone = form_value("phone", maximum=20) or None
                role_id = form_int("role_id", minimum=1)
                password = request.form.get("password", "")
                if len(password) < 8 or len(password.encode("utf-8")) > 72:
                    raise DashboardInputError("Mật khẩu nhân viên cần từ 8 ký tự (tối đa 72 byte).")
                connection.execute(
                    text(
                        "INSERT INTO Users "
                        "(RoleID, Username, PasswordHash, FullName, Email, Phone) "
                        "VALUES (:role_id, :username, :password_hash, :full_name, :email, :phone)"
                    ),
                    {
                        "role_id": role_id,
                        "username": username,
                        "password_hash": bcrypt.hashpw(
                            password.encode("utf-8"), bcrypt.gensalt()
                        ).decode("utf-8"),
                        "full_name": full_name,
                        "email": email,
                        "phone": phone,
                    },
                )
                flash("Đã tạo tài khoản nhân viên.", "success")

            elif action == "employee-update":
                user_id = form_int("id", minimum=1)
                role_id = form_int("role_id", minimum=1)
                values = {
                    "id": user_id,
                    "role_id": role_id,
                    "full_name": form_value("full_name", required=True, maximum=100),
                    "email": form_value("email", maximum=100) or None,
                    "phone": form_value("phone", maximum=20) or None,
                }
                password = request.form.get("password", "")
                if password:
                    if len(password) < 8 or len(password.encode("utf-8")) > 72:
                        raise DashboardInputError("Mật khẩu cần từ 8 ký tự (tối đa 72 byte).")
                    connection.execute(
                        text(
                            "UPDATE Users SET RoleID=:role_id, FullName=:full_name, "
                            "Email=:email, Phone=:phone, PasswordHash=:password_hash "
                            "WHERE UserID=:id AND IsDeleted=0"
                        ),
                        {
                            **values,
                            "password_hash": bcrypt.hashpw(
                                password.encode("utf-8"), bcrypt.gensalt()
                            ).decode("utf-8"),
                        },
                    )
                else:
                    connection.execute(
                        text(
                            "UPDATE Users SET RoleID=:role_id, FullName=:full_name, "
                            "Email=:email, Phone=:phone "
                            "WHERE UserID=:id AND IsDeleted=0"
                        ),
                        values,
                    )
                flash("Đã cập nhật tài khoản nhân viên.", "success")

            elif action == "employee-delete":
                user_id = form_int("id", minimum=1)
                if user_id == session.get("user_id"):
                    raise DashboardInputError("Không thể tự khóa tài khoản đang sử dụng.")
                connection.execute(
                    text(
                        "UPDATE Users SET IsDeleted=1, DeletedAt=CURRENT_TIMESTAMP "
                        "WHERE UserID=:id AND IsDeleted=0"
                    ),
                    {"id": user_id},
                )
                flash("Đã khóa tài khoản nhân viên.", "success")

            elif action in {"customer-create", "customer-update"}:
                customer_id = (
                    form_int("id", minimum=1) if action == "customer-update" else None
                )
                values = {
                    "id": customer_id,
                    "full_name": form_value("full_name", required=True, maximum=100),
                    "phone": form_value("phone", required=True, maximum=20),
                    "email": form_value("email", maximum=100) or None,
                }
                password = request.form.get("password", "")
                if action == "customer-create":
                    if len(password) < 8 or len(password.encode("utf-8")) > 72:
                        raise DashboardInputError("Mật khẩu cần từ 8 ký tự (tối đa 72 byte).")
                    connection.execute(
                        text(
                            "INSERT INTO Customers "
                            "(FullName, Phone, Email, PasswordHash) "
                            "VALUES (:full_name, :phone, :email, :password_hash)"
                        ),
                        {
                            **values,
                            "password_hash": bcrypt.hashpw(
                                password.encode("utf-8"), bcrypt.gensalt()
                            ).decode("utf-8"),
                        },
                    )
                    flash("Đã tạo khách hàng.", "success")
                elif password:
                    if len(password) < 8 or len(password.encode("utf-8")) > 72:
                        raise DashboardInputError("Mật khẩu cần từ 8 ký tự (tối đa 72 byte).")
                    connection.execute(
                        text(
                            "UPDATE Customers SET FullName=:full_name, Phone=:phone, "
                            "Email=:email, PasswordHash=:password_hash "
                            "WHERE CustomerID=:id AND IsDeleted=0"
                        ),
                        {
                            **values,
                            "password_hash": bcrypt.hashpw(
                                password.encode("utf-8"), bcrypt.gensalt()
                            ).decode("utf-8"),
                        },
                    )
                    flash("Đã cập nhật khách hàng và mật khẩu.", "success")
                else:
                    connection.execute(
                        text(
                            "UPDATE Customers SET FullName=:full_name, Phone=:phone, "
                            "Email=:email WHERE CustomerID=:id AND IsDeleted=0"
                        ),
                        values,
                    )
                    flash("Đã cập nhật khách hàng.", "success")

            elif action == "customer-delete":
                connection.execute(
                    text(
                        "UPDATE Customers SET IsDeleted=1, DeletedAt=CURRENT_TIMESTAMP "
                        "WHERE CustomerID=:id AND IsDeleted=0"
                    ),
                    {"id": form_int("id", minimum=1)},
                )
                flash("Đã ẩn khách hàng.", "success")

            elif action in {"product-create", "product-update"}:
                product_id = (
                    form_int("id", minimum=1) if action == "product-update" else None
                )
                values = {
                    "sku": form_value("sku", required=True, maximum=50),
                    "barcode": form_value("barcode", maximum=50) or None,
                    "product_name": form_value("product_name", required=True, maximum=200),
                    "category_id": form_int("category_id", minimum=1, optional=True),
                    "supplier_id": form_int("supplier_id", minimum=1, optional=True),
                    "main_image": form_value("main_image", maximum=500) or None,
                    "specifications": form_value("specifications") or None,
                    "cost_price": form_decimal("cost_price"),
                    "selling_price": form_decimal("selling_price"),
                    "warranty_months": form_int("warranty_months", minimum=0),
                    "is_has_serial": 1 if request.form.get("is_has_serial") == "1" else 0,
                }
                if action == "product-create":
                    connection.execute(
                        text(
                            "INSERT INTO Products "
                            "(SKU, Barcode, ProductName, CategoryID, SupplierID, MainImage, "
                            "Specifications, CostPrice, SellingPrice, StockQuantity, "
                            "WarrantyMonths, IsHasSerial) "
                            "VALUES (:sku, :barcode, :product_name, :category_id, :supplier_id, "
                            ":main_image, :specifications, :cost_price, :selling_price, 0, "
                            ":warranty_months, :is_has_serial)"
                        ),
                        values,
                    )
                    flash("Đã tạo sản phẩm. Tồn kho ban đầu là 0; dùng phiếu nhập để bổ sung hàng.", "success")
                else:
                    connection.execute(
                        text(
                            "UPDATE Products SET SKU=:sku, Barcode=:barcode, "
                            "ProductName=:product_name, CategoryID=:category_id, "
                            "SupplierID=:supplier_id, MainImage=:main_image, "
                            "Specifications=:specifications, CostPrice=:cost_price, "
                            "SellingPrice=:selling_price, WarrantyMonths=:warranty_months, "
                            "IsHasSerial=:is_has_serial "
                            "WHERE ProductID=:id AND IsDeleted=0"
                        ),
                        {**values, "id": product_id},
                    )
                    flash("Đã cập nhật sản phẩm.", "success")

            elif action == "product-delete":
                connection.execute(
                    text(
                        "UPDATE Products SET IsDeleted=1, DeletedAt=CURRENT_TIMESTAMP "
                        "WHERE ProductID=:id AND IsDeleted=0"
                    ),
                    {"id": form_int("id", minimum=1)},
                )
                flash("Đã ẩn sản phẩm.", "success")

            elif action == "inbound-create":
                product_id = form_int("product_id", minimum=1)
                supplier_id = form_int("supplier_id", minimum=1, optional=True)
                quantity = form_int("quantity", minimum=1)
                import_price = form_decimal("import_price")
                product = connection.execute(
                    text(
                        "SELECT ProductID, IsHasSerial FROM Products "
                        "WHERE ProductID=:id AND IsDeleted=0 FOR UPDATE"
                    ),
                    {"id": product_id},
                ).first()
                if not product:
                    raise DashboardInputError("Không tìm thấy sản phẩm cần nhập.")
                serial_numbers = [
                    serial.strip()
                    for serial in request.form.get("serial_numbers", "").splitlines()
                    if serial.strip()
                ]
                if product["IsHasSerial"] and len(serial_numbers) != quantity:
                    raise DashboardInputError(
                        "Số serial nhập vào phải đúng bằng số lượng hàng nhập."
                    )
                if any(len(serial) > 100 for serial in serial_numbers):
                    raise DashboardInputError("Mỗi số serial tối đa 100 ký tự.")
                total = import_price * quantity
                note = connection.execute(
                    text(
                        "INSERT INTO Inbound_Notes "
                        "(SupplierID, CreatedBy, TotalAmount, Status, Notes) "
                        "VALUES (:supplier_id, :created_by, :total, 'COMPLETED', :notes)"
                    ),
                    {
                        "supplier_id": supplier_id,
                        "created_by": session["user_id"],
                        "total": total,
                        "notes": form_value("notes") or None,
                    },
                )
                detail = connection.execute(
                    text(
                        "INSERT INTO Inbound_Details "
                        "(InboundID, ProductID, Quantity, ImportPrice) "
                        "VALUES (:inbound_id, :product_id, :quantity, :price)"
                    ),
                    {
                        "inbound_id": note.lastrowid,
                        "product_id": product_id,
                        "quantity": quantity,
                        "price": import_price,
                    },
                )
                for serial_number in serial_numbers:
                    connection.execute(
                        text(
                            "INSERT INTO Product_Serials "
                            "(ProductID, SerialNumber, Status, InboundDetailID) "
                            "VALUES (:product_id, :serial_number, 'AVAILABLE', :detail_id)"
                        ),
                        {
                            "product_id": product_id,
                            "serial_number": serial_number,
                            "detail_id": detail.lastrowid,
                        },
                    )
                connection.execute(
                    text(
                        "UPDATE Products SET StockQuantity=COALESCE(StockQuantity, 0)+:quantity, "
                        "CostPrice=:price WHERE ProductID=:product_id"
                    ),
                    {"quantity": quantity, "price": import_price, "product_id": product_id},
                )
                flash(f"Đã tạo phiếu nhập #{note.lastrowid}.", "success")

            elif action == "outbound-create":
                product_id = form_int("product_id", minimum=1)
                customer_id = form_int("customer_id", minimum=1, optional=True)
                quantity = form_int("quantity", minimum=1)
                payment_method = form_value("payment_method", required=True, maximum=20)
                if payment_method not in {"CASH", "BANK_TRANSFER", "CARD", "MOMO", "VNPAY"}:
                    raise DashboardInputError("Phương thức thanh toán không hợp lệ.")
                product = connection.execute(
                    text(
                        "SELECT SellingPrice, StockQuantity, IsHasSerial FROM Products "
                        "WHERE ProductID=:id AND IsDeleted=0 FOR UPDATE"
                    ),
                    {"id": product_id},
                ).mappings().first()
                if not product:
                    raise DashboardInputError("Không tìm thấy sản phẩm cần xuất.")
                if (product["StockQuantity"] or 0) < quantity:
                    raise DashboardInputError("Số lượng xuất vượt quá tồn kho.")
                available_serials = []
                if product["IsHasSerial"]:
                    available_serials = connection.execute(
                        text(
                            "SELECT SerialID FROM Product_Serials "
                            "WHERE ProductID=:product_id AND Status='AVAILABLE' "
                            "ORDER BY SerialID LIMIT :quantity FOR UPDATE"
                        ),
                        {"product_id": product_id, "quantity": quantity},
                    ).mappings().all()
                    if len(available_serials) != quantity:
                        raise DashboardInputError(
                            "Không đủ serial còn khả dụng để xuất sản phẩm này."
                        )
                amount = Decimal(product["SellingPrice"]) * quantity
                order_code = f"HD{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(2).upper()}"
                order = connection.execute(
                    text(
                        "INSERT INTO Orders "
                        "(OrderCode, CustomerID, EmployeeID, SubTotal, DiscountAmount, "
                        "TotalAmount, OrderStatus, Notes) "
                        "VALUES (:code, :customer_id, :employee_id, :amount, 0, "
                        ":amount, 'PAID', :notes)"
                    ),
                    {
                        "code": order_code,
                        "customer_id": customer_id,
                        "employee_id": session["user_id"],
                        "amount": amount,
                        "notes": form_value("notes") or None,
                    },
                )
                order_detail = connection.execute(
                    text(
                        "INSERT INTO Order_Details "
                        "(OrderID, ProductID, Quantity, UnitPrice, TotalPrice) "
                        "VALUES (:order_id, :product_id, :quantity, :price, :total)"
                    ),
                    {
                        "order_id": order.lastrowid,
                        "product_id": product_id,
                        "quantity": quantity,
                        "price": product["SellingPrice"],
                        "total": amount,
                    },
                )
                for serial in available_serials:
                    connection.execute(
                        text(
                            "UPDATE Product_Serials SET Status='SOLD', OrderDetailID=:detail_id "
                            "WHERE SerialID=:serial_id AND Status='AVAILABLE'"
                        ),
                        {
                            "detail_id": order_detail.lastrowid,
                            "serial_id": serial["SerialID"],
                        },
                    )
                connection.execute(
                    text(
                        "UPDATE Products SET StockQuantity=COALESCE(StockQuantity, 0)-:quantity "
                        "WHERE ProductID=:product_id"
                    ),
                    {"quantity": quantity, "product_id": product_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO Payments "
                        "(OrderID, Amount, PaidAmount, PaymentMethod, PaymentStatus) "
                        "VALUES (:order_id, :amount, :amount, :method, 'PAID')"
                    ),
                    {
                        "order_id": order.lastrowid,
                        "amount": amount,
                        "method": payment_method,
                    },
                )
                if customer_id:
                    connection.execute(
                        text(
                            "UPDATE Customers SET TotalSpent=COALESCE(TotalSpent, 0)+:amount "
                            "WHERE CustomerID=:customer_id AND IsDeleted=0"
                        ),
                        {"amount": amount, "customer_id": customer_id},
                    )
                flash(f"Đã tạo đơn xuất hàng {order_code}.", "success")
            else:
                abort(404)
    except DashboardInputError as error:
        flash(str(error), "error")
    except IntegrityError:
        logger.exception("Vi phạm ràng buộc khi quản lý dashboard")
        flash("Dữ liệu trùng lặp hoặc tham chiếu không hợp lệ.", "error")
    except Exception:
        logger.exception("Không thể hoàn tất thao tác dashboard: %s", action)
        flash("Không thể hoàn tất thao tác. Kiểm tra cơ sở dữ liệu và thử lại.", "error")

    return redirect(url_for("dashboard.home") + f"#{action.split('-')[0]}-section")
