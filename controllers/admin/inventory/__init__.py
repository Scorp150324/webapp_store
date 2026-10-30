import secrets
from datetime import datetime
from decimal import Decimal

from flask import flash, request, session
from sqlalchemy import text

from controllers.admin.common import DashboardInputError, form_decimal, form_int, form_value


def handle_action(connection, action):
    if action == "inbound-create":
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
        if len(serial_numbers) != len(set(serial_numbers)):
            raise DashboardInputError("Số serial nhập vào không được trùng lặp.")
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
        return

    if action == "outbound-create":
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
        return

    raise ValueError(f"Unsupported inventory action: {action}")
