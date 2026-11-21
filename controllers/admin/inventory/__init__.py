import secrets
from datetime import datetime
from decimal import Decimal

from flask import flash, request, session
from database import insert_id, text
from controllers.admin.common import DashboardInputError, form_decimal, form_int, form_value


def _lock_product(connection, product_id):
    return connection.execute(
        text(
            "SELECT ProductID, StockQuantity, IsHasSerial FROM Products "
            "WHERE ProductID=:id FOR UPDATE"
        ),
        {"id": product_id},
    ).mappings().first()


def _reverse_inbound_stock(connection, inbound_id):
    details = connection.execute(
        text(
            "SELECT InboundDetailID, ProductID, Quantity FROM Inbound_Details "
            "WHERE InboundID=:id ORDER BY InboundDetailID FOR UPDATE"
        ),
        {"id": inbound_id},
    ).mappings().all()
    for detail in details:
        product = _lock_product(connection, detail["ProductID"])
        quantity = detail["Quantity"]
        if not product or (product["StockQuantity"] or 0) < quantity:
            raise DashboardInputError(
                "Không thể hủy phiếu nhập vì tồn kho hiện tại không đủ để hoàn tác."
            )

        serials = connection.execute(
            text(
                "SELECT SerialID, Status, OrderDetailID FROM Product_Serials "
                "WHERE InboundDetailID=:detail_id FOR UPDATE"
            ),
            {"detail_id": detail["InboundDetailID"]},
        ).mappings().all()
        if any(row["Status"] != "AVAILABLE" or row["OrderDetailID"] is not None for row in serials):
            raise DashboardInputError(
                "Không thể hủy phiếu nhập vì serial của phiếu đã được xuất hoặc thay đổi."
            )

        connection.execute(
            text(
                "UPDATE Products SET StockQuantity=COALESCE(StockQuantity, 0)-:quantity "
                "WHERE ProductID=:product_id"
            ),
            {"quantity": quantity, "product_id": detail["ProductID"]},
        )
        if serials:
            connection.execute(
                text(
                    "UPDATE Product_Serials SET Status='REMOVED' "
                    "WHERE InboundDetailID=:detail_id AND Status='AVAILABLE'"
                ),
                {"detail_id": detail["InboundDetailID"]},
            )


def _apply_inbound_stock(connection, inbound_id):
    details = connection.execute(
        text(
            "SELECT InboundDetailID, ProductID, Quantity FROM Inbound_Details "
            "WHERE InboundID=:id ORDER BY InboundDetailID FOR UPDATE"
        ),
        {"id": inbound_id},
    ).mappings().all()
    for detail in details:
        if not _lock_product(connection, detail["ProductID"]):
            raise DashboardInputError("Không tìm thấy sản phẩm trong phiếu nhập.")
        connection.execute(
            text(
                "UPDATE Products SET StockQuantity=COALESCE(StockQuantity, 0)+:quantity "
                "WHERE ProductID=:product_id"
            ),
            {"quantity": detail["Quantity"], "product_id": detail["ProductID"]},
        )
        connection.execute(
            text(
                "UPDATE Product_Serials SET Status='AVAILABLE' "
                "WHERE InboundDetailID=:detail_id AND Status='REMOVED'"
            ),
            {"detail_id": detail["InboundDetailID"]},
        )


def _reverse_outbound_stock(connection, order_id):
    details = connection.execute(
        text(
            "SELECT OrderDetailID, ProductID, Quantity FROM Order_Details "
            "WHERE OrderID=:id ORDER BY OrderDetailID FOR UPDATE"
        ),
        {"id": order_id},
    ).mappings().all()
    for detail in details:
        product = _lock_product(connection, detail["ProductID"])
        if not product:
            raise DashboardInputError("Không tìm thấy sản phẩm trong đơn xuất.")
        serials = connection.execute(
            text(
                "SELECT SerialID, Status FROM Product_Serials "
                "WHERE OrderDetailID=:detail_id FOR UPDATE"
            ),
            {"detail_id": detail["OrderDetailID"]},
        ).mappings().all()
        if product["IsHasSerial"] and (
            len(serials) != detail["Quantity"]
            or any(row["Status"] != "SOLD" for row in serials)
        ):
            raise DashboardInputError(
                "Không thể hoàn tác đơn xuất vì serial đã được sử dụng hoặc thay đổi."
            )

        connection.execute(
            text(
                "UPDATE Products SET StockQuantity=COALESCE(StockQuantity, 0)+:quantity "
                "WHERE ProductID=:product_id"
            ),
            {"quantity": detail["Quantity"], "product_id": detail["ProductID"]},
        )
        connection.execute(
            text(
                "UPDATE Product_Serials SET Status='AVAILABLE', OrderDetailID=NULL "
                "WHERE OrderDetailID=:detail_id AND Status='SOLD'"
            ),
            {"detail_id": detail["OrderDetailID"]},
        )


def _apply_outbound_stock(connection, order_id):
    details = connection.execute(
        text(
            "SELECT OrderDetailID, ProductID, Quantity FROM Order_Details "
            "WHERE OrderID=:id ORDER BY OrderDetailID FOR UPDATE"
        ),
        {"id": order_id},
    ).mappings().all()
    for detail in details:
        product = _lock_product(connection, detail["ProductID"])
        quantity = detail["Quantity"]
        if not product or (product["StockQuantity"] or 0) < quantity:
            raise DashboardInputError("Không đủ tồn kho để khôi phục đơn xuất này.")

        if product["IsHasSerial"]:
            serials = connection.execute(
                text(
                    "SELECT SerialID FROM Product_Serials "
                    "WHERE ProductID=:product_id AND Status='AVAILABLE' "
                    "ORDER BY SerialID LIMIT :quantity FOR UPDATE"
                ),
                {"product_id": detail["ProductID"], "quantity": quantity},
            ).mappings().all()
            if len(serials) != quantity:
                raise DashboardInputError(
                    "Không đủ serial khả dụng để khôi phục đơn xuất này."
                )
            for serial in serials:
                connection.execute(
                    text(
                        "UPDATE Product_Serials SET Status='SOLD', OrderDetailID=:detail_id "
                        "WHERE SerialID=:serial_id AND Status='AVAILABLE'"
                    ),
                    {"detail_id": detail["OrderDetailID"], "serial_id": serial["SerialID"]},
                )

        connection.execute(
            text(
                "UPDATE Products SET StockQuantity=COALESCE(StockQuantity, 0)-:quantity "
                "WHERE ProductID=:product_id"
            ),
            {"quantity": quantity, "product_id": detail["ProductID"]},
        )


def handle_action(connection, action):
    if action == "inbound-update":
        inbound_id = form_int("id", minimum=1)
        supplier_id = form_int("supplier_id", minimum=1, optional=True)
        status = form_value("status", required=True, maximum=20)
        if status not in {"DRAFT", "COMPLETED", "CANCELLED"}:
            raise DashboardInputError("Trạng thái phiếu nhập không hợp lệ.")
        note = connection.execute(
            text(
                "SELECT InboundID, Status FROM Inbound_Notes "
                "WHERE InboundID=:id AND COALESCE(Status, '') NOT LIKE 'DELETED%' "
                "FOR UPDATE"
            ),
            {"id": inbound_id},
        ).mappings().first()
        if not note:
            raise DashboardInputError("Không tìm thấy phiếu nhập đang hoạt động.")
        if note["Status"] == "COMPLETED" and status != "COMPLETED":
            _reverse_inbound_stock(connection, inbound_id)
        elif note["Status"] != "COMPLETED" and status == "COMPLETED":
            _apply_inbound_stock(connection, inbound_id)
        connection.execute(
            text(
                "UPDATE Inbound_Notes SET SupplierID=:supplier_id, Status=:status, "
                "Notes=:notes WHERE InboundID=:id "
                "AND COALESCE(Status, '') NOT LIKE 'DELETED%'"
            ),
            {
                "supplier_id": supplier_id,
                "status": status,
                "notes": form_value("notes") or None,
                "id": inbound_id,
            },
        )
        flash(f"Đã cập nhật phiếu nhập #{inbound_id}. Tồn kho được đồng bộ theo trạng thái.", "success")
        return

    if action == "inbound-delete":
        inbound_id = form_int("id", minimum=1)
        note = connection.execute(
            text(
                "SELECT Status FROM Inbound_Notes "
                "WHERE InboundID=:id AND COALESCE(Status, '') NOT LIKE 'DELETED%' "
                "FOR UPDATE"
            ),
            {"id": inbound_id},
        ).mappings().first()
        if not note:
            raise DashboardInputError("Không tìm thấy phiếu nhập đang hoạt động.")
        deleted_status = note["Status"]
        if deleted_status not in {"DRAFT", "COMPLETED", "CANCELLED"}:
            deleted_status = "COMPLETED"
        if deleted_status == "COMPLETED":
            _reverse_inbound_stock(connection, inbound_id)
        connection.execute(
            text(
                "UPDATE Inbound_Notes SET Status=:deleted_status "
                "WHERE InboundID=:id AND COALESCE(Status, '') NOT LIKE 'DELETED%'"
            ),
            {"id": inbound_id, "deleted_status": f"DELETED:{deleted_status}"},
        )
        message = (
            "số lượng đã được trừ khỏi tồn kho"
            if deleted_status == "COMPLETED"
            else "tồn kho không thay đổi"
        )
        flash(f"Đã ẩn phiếu nhập #{inbound_id}; {message}.", "success")
        return

    if action == "inbound-restore":
        inbound_id = form_int("id", minimum=1)
        note = connection.execute(
            text(
                "SELECT Status FROM Inbound_Notes "
                "WHERE InboundID=:id AND COALESCE(Status, '') LIKE 'DELETED%' "
                "FOR UPDATE"
            ),
            {"id": inbound_id},
        ).mappings().first()
        if not note:
            raise DashboardInputError("Không tìm thấy phiếu nhập đã xóa.")
        _, separator, previous_status = (note["Status"] or "").partition(":")
        if not separator or previous_status not in {"DRAFT", "COMPLETED", "CANCELLED"}:
            previous_status = "COMPLETED"
        if previous_status == "COMPLETED":
            _apply_inbound_stock(connection, inbound_id)
        connection.execute(
            text(
                "UPDATE Inbound_Notes SET Status=:status "
                "WHERE InboundID=:id AND COALESCE(Status, '') LIKE 'DELETED%'"
            ),
            {"id": inbound_id, "status": previous_status},
        )
        message = (
            "số lượng đã được cộng lại vào tồn kho"
            if previous_status == "COMPLETED"
            else "tồn kho không thay đổi"
        )
        flash(f"Đã khôi phục phiếu nhập #{inbound_id}; {message}.", "success")
        return

    if action == "outbound-update":
        order_id = form_int("id", minimum=1)
        status = form_value("status", required=True, maximum=20)
        if status not in {"PENDING", "PAID", "SHIPPED", "COMPLETED", "CANCELLED"}:
            raise DashboardInputError("Trạng thái đơn xuất không hợp lệ.")
        order = connection.execute(
            text(
                "SELECT OrderID, OrderStatus FROM Orders "
                "WHERE OrderID=:id AND COALESCE(OrderStatus, '') NOT LIKE 'DELETED%' "
                "FOR UPDATE"
            ),
            {"id": order_id},
        ).mappings().first()
        if not order:
            raise DashboardInputError("Không tìm thấy đơn xuất đang hoạt động.")
        if order["OrderStatus"] == "CANCELLED" and status != "CANCELLED":
            _apply_outbound_stock(connection, order_id)
        elif order["OrderStatus"] != "CANCELLED" and status == "CANCELLED":
            _reverse_outbound_stock(connection, order_id)
        connection.execute(
            text(
                "UPDATE Orders SET OrderStatus=:status, Notes=:notes "
                "WHERE OrderID=:id AND COALESCE(OrderStatus, '') NOT LIKE 'DELETED%'"
            ),
            {
                "status": status,
                "notes": form_value("notes") or None,
                "id": order_id,
            },
        )
        flash(f"Đã cập nhật đơn xuất #{order_id}. Tồn kho được đồng bộ theo trạng thái.", "success")
        return

    if action == "outbound-delete":
        order_id = form_int("id", minimum=1)
        order = connection.execute(
            text(
                "SELECT OrderStatus FROM Orders "
                "WHERE OrderID=:id AND COALESCE(OrderStatus, '') NOT LIKE 'DELETED%' "
                "FOR UPDATE"
            ),
            {"id": order_id},
        ).mappings().first()
        if not order:
            raise DashboardInputError("Không tìm thấy đơn xuất đang hoạt động.")
        deleted_status = order["OrderStatus"]
        if deleted_status not in {"PENDING", "PAID", "SHIPPED", "COMPLETED", "CANCELLED"}:
            deleted_status = "PAID"
        if deleted_status != "CANCELLED":
            _reverse_outbound_stock(connection, order_id)
        connection.execute(
            text(
                "UPDATE Orders SET OrderStatus=:deleted_status "
                "WHERE OrderID=:id AND COALESCE(OrderStatus, '') NOT LIKE 'DELETED%'"
            ),
            {"id": order_id, "deleted_status": f"DELETED:{deleted_status}"},
        )
        message = (
            "hàng đã được cộng lại vào tồn kho"
            if deleted_status != "CANCELLED"
            else "tồn kho không thay đổi"
        )
        flash(f"Đã ẩn đơn xuất #{order_id}; {message}.", "success")
        return

    if action == "outbound-restore":
        order_id = form_int("id", minimum=1)
        order = connection.execute(
            text(
                "SELECT OrderStatus FROM Orders "
                "WHERE OrderID=:id AND COALESCE(OrderStatus, '') LIKE 'DELETED%' "
                "FOR UPDATE"
            ),
            {"id": order_id},
        ).mappings().first()
        if not order:
            raise DashboardInputError("Không tìm thấy đơn xuất đã xóa.")
        _, separator, previous_status = (order["OrderStatus"] or "").partition(":")
        if not separator or previous_status not in {
            "PENDING", "PAID", "SHIPPED", "COMPLETED", "CANCELLED"
        }:
            previous_status = "PAID"
        if previous_status != "CANCELLED":
            _apply_outbound_stock(connection, order_id)
        connection.execute(
            text(
                "UPDATE Orders SET OrderStatus=:status "
                "WHERE OrderID=:id AND COALESCE(OrderStatus, '') LIKE 'DELETED%'"
            ),
            {"id": order_id, "status": previous_status},
        )
        message = (
            "hàng đã được trừ khỏi tồn kho"
            if previous_status != "CANCELLED"
            else "tồn kho không thay đổi"
        )
        flash(f"Đã khôi phục đơn xuất #{order_id}; {message}.", "success")
        return

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
        ).mappings().first()
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
        note_id = insert_id(
            connection,
            "INSERT INTO Inbound_Notes "
            "(SupplierID, CreatedBy, TotalAmount, Status, Notes) "
            "VALUES (:supplier_id, :created_by, :total, 'COMPLETED', :notes)",
            {
                "supplier_id": supplier_id,
                "created_by": session["user_id"],
                "total": total,
                "notes": form_value("notes") or None,
            },
            "InboundID",
        )
        detail_id = insert_id(
            connection,
            "INSERT INTO Inbound_Details "
            "(InboundID, ProductID, Quantity, ImportPrice) "
            "VALUES (:inbound_id, :product_id, :quantity, :price)",
            {
                "inbound_id": note_id,
                "product_id": product_id,
                "quantity": quantity,
                "price": import_price,
            },
            "InboundDetailID",
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
                    "detail_id": detail_id,
                },
            )
        connection.execute(
            text(
                "UPDATE Products SET StockQuantity=COALESCE(StockQuantity, 0)+:quantity, "
                "CostPrice=:price WHERE ProductID=:product_id"
            ),
            {"quantity": quantity, "price": import_price, "product_id": product_id},
        )
        flash(f"Đã tạo phiếu nhập #{note_id}.", "success")
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
                "SELECT ProductName, SellingPrice, StockQuantity, IsHasSerial FROM Products "
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
                    f"Sản phẩm {product['ProductName']} chỉ còn "
                    f"{len(available_serials)} serial khả dụng; bạn đang xuất {quantity}."
                )

        amount = Decimal(product["SellingPrice"]) * quantity
        order_code = f"HD{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(2).upper()}"
        order_id = insert_id(
            connection,
            "INSERT INTO Orders "
            "(OrderCode, CustomerID, EmployeeID, SubTotal, DiscountAmount, "
            "TotalAmount, OrderStatus, Notes) "
            "VALUES (:code, :customer_id, :employee_id, :amount, 0, "
            ":amount, 'PAID', :notes)",
            {
                "code": order_code,
                "customer_id": customer_id,
                "employee_id": session["user_id"],
                "amount": amount,
                "notes": form_value("notes") or None,
            },
            "OrderID",
        )
        order_detail_id = insert_id(
            connection,
            "INSERT INTO Order_Details "
            "(OrderID, ProductID, Quantity, UnitPrice, TotalPrice) "
            "VALUES (:order_id, :product_id, :quantity, :price, :total)",
            {
                "order_id": order_id,
                "product_id": product_id,
                "quantity": quantity,
                "price": product["SellingPrice"],
                "total": amount,
            },
            "OrderDetailID",
        )
        for serial in available_serials:
            connection.execute(
                text(
                    "UPDATE Product_Serials SET Status='SOLD', OrderDetailID=:detail_id "
                    "WHERE SerialID=:serial_id AND Status='AVAILABLE'"
                ),
                {
                    "detail_id": order_detail_id,
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
                "order_id": order_id,
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
