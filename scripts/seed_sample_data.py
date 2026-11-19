import hashlib
import os
import secrets
from datetime import date, datetime, timedelta
from decimal import Decimal

import bcrypt
from sqlalchemy import inspect

from database import engine, text


TARGET_ROWS = 100
TABLES = (
    "Roles",
    "Permissions",
    "Role_Permissions",
    "Users",
    "User_Logs",
    "Customer_Groups",
    "Customers",
    "Password_Reset_Tokens",
    "Customer_Login_Logs",
    "Customer_Addresses",
    "Promotions",
    "Categories",
    "Suppliers",
    "Products",
    "Product_Images",
    "Product_Serials",
    "Inbound_Notes",
    "Inbound_Details",
    "Orders",
    "Order_Details",
    "Payments",
    "Payment_Transactions",
    "Warranties",
)


def _count(connection, table):
    return connection.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar_one()


def _ids(connection, table, column):
    return connection.execute(
        text(f"SELECT `{column}` FROM `{table}` ORDER BY `{column}`")
    ).scalars().all()


def _next_id(connection, table, column):
    current_max = connection.execute(
        text(f"SELECT COALESCE(MAX(`{column}`), 0) FROM `{table}`")
    ).scalar_one()
    return int(current_max) + 1


def _seed_rows(connection, table, primary_key, make_row):
    missing = max(TARGET_ROWS - _count(connection, table), 0)
    if not missing:
        return

    start_id = _next_id(connection, table, primary_key)
    rows = [make_row(start_id + offset) for offset in range(missing)]
    columns = tuple(rows[0])
    column_sql = ", ".join(f"`{column}`" for column in columns)
    value_sql = ", ".join(f":{column}" for column in columns)
    connection.execute(
        text(f"INSERT INTO `{table}` ({column_sql}) VALUES ({value_sql})"),
        rows,
    )


def _seed_role_permissions(connection, role_ids, permission_ids):
    existing_rows = connection.execute(
        text("SELECT RoleID, PermissionID FROM Role_Permissions")
    ).all()
    existing = {(row[0], row[1]) for row in existing_rows}
    missing = max(TARGET_ROWS - len(existing), 0)
    if not missing:
        return
    rows = []

    for role_id in role_ids:
        for permission_id in permission_ids:
            pair = (role_id, permission_id)
            if pair not in existing:
                rows.append({"RoleID": role_id, "PermissionID": permission_id})
                existing.add(pair)
                if len(rows) == missing:
                    break
        if len(rows) == missing:
            break

    if len(rows) != missing:
        raise RuntimeError("Not enough unique role/permission pairs to seed the table")
    if rows:
        connection.execute(
            text(
                "INSERT INTO Role_Permissions (RoleID, PermissionID) "
                "VALUES (:RoleID, :PermissionID)"
            ),
            rows,
        )


def _ensure_search_indexes():
    definitions = {
        "idx_products_active_name_prefix": (
            "CREATE INDEX idx_products_active_name_prefix "
            "ON Products (IsDeleted, ProductName)"
        ),
        "idx_products_active_specs_prefix": (
            "CREATE INDEX idx_products_active_specs_prefix "
            "ON Products (IsDeleted, Specifications(191))"
        ),
    }
    indexes = {
        index["name"].lower()
        for index in inspect(engine).get_indexes("Products")
    }
    with engine.connect() as connection:
        for name, statement in definitions.items():
            if name.lower() not in indexes:
                connection.execute(text(statement))
        connection.commit()


def _require_local_mysql():
    if engine.dialect.name != "mysql":
        raise RuntimeError("Sample data can only be seeded into MySQL.")
    if engine.url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Refusing to seed a non-local database.")
    if os.environ.get("VERCEL") or os.environ.get("FLASK_ENV", "").lower() == "production":
        raise RuntimeError("Sample data cannot be seeded in production.")


def seed_sample_data():
    now = datetime.now().replace(microsecond=0)
    sample_hash = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode("ascii")
    with engine.begin() as connection:
        _seed_rows(
            connection,
            "Roles",
            "RoleID",
            lambda row_id: {
                "RoleID": row_id,
                "RoleName": f"SAMPLE_ROLE_{row_id:04d}",
                "Description": "Vai tro du lieu mau",
            },
        )
        _seed_rows(
            connection,
            "Permissions",
            "PermissionID",
            lambda row_id: {
                "PermissionID": row_id,
                "PermissionCode": f"SAMPLE_PERMISSION_{row_id:04d}",
                "PermissionName": f"Quyen mau {row_id}",
                "Module": "SAMPLE",
            },
        )
        _seed_rows(
            connection,
            "Customer_Groups",
            "GroupID",
            lambda row_id: {
                "GroupID": row_id,
                "GroupName": f"Nhom khach hang mau {row_id}",
                "DiscountPercent": Decimal(row_id % 20),
                "MinSpent": Decimal(row_id * 100000),
            },
        )
        _seed_rows(
            connection,
            "Categories",
            "CategoryID",
            lambda row_id: {
                "CategoryID": row_id,
                "CategoryName": f"Danh muc mau {row_id}",
                "Description": "Danh muc phuc vu kiem thu",
            },
        )
        _seed_rows(
            connection,
            "Suppliers",
            "SupplierID",
            lambda row_id: {
                "SupplierID": row_id,
                "SupplierName": f"Nha cung cap mau {row_id}",
                "Phone": f"028{row_id:08d}",
                "Email": f"supplier.{row_id}@example.invalid",
                "Address": f"Dia chi mau {row_id}",
                "TaxCode": f"TAX-SAMPLE-{row_id:06d}",
            },
        )

        group_ids = _ids(connection, "Customer_Groups", "GroupID")
        role_ids = _ids(connection, "Roles", "RoleID")
        permission_ids = _ids(connection, "Permissions", "PermissionID")
        supplier_ids = _ids(connection, "Suppliers", "SupplierID")
        category_ids = _ids(connection, "Categories", "CategoryID")

        _seed_rows(
            connection,
            "Users",
            "UserID",
            lambda row_id: {
                "UserID": row_id,
                "RoleID": role_ids[row_id % len(role_ids)],
                "Username": f"sample_employee_{row_id:05d}",
                "PasswordHash": sample_hash,
                "FullName": f"Nhan vien mau {row_id}",
                "Email": f"employee.{row_id}@example.invalid",
                "Phone": f"0289{row_id:07d}",
                "IsDeleted": 0,
            },
        )
        user_ids = _ids(connection, "Users", "UserID")
        _seed_rows(
            connection,
            "Customers",
            "CustomerID",
            lambda row_id: {
                "CustomerID": row_id,
                "GroupID": group_ids[row_id % len(group_ids)],
                "FullName": f"Khach hang mau {row_id}",
                "Username": f"sample_customer_{row_id:05d}",
                "Phone": f"099{row_id:08d}",
                "Email": f"customer.{row_id}@example.invalid",
                "TotalSpent": Decimal(row_id * 250000),
                "RewardPoints": row_id * 10,
                "IsDeleted": 0,
            },
        )
        customer_ids = _ids(connection, "Customers", "CustomerID")
        _seed_rows(
            connection,
            "Promotions",
            "PromotionID",
            lambda row_id: {
                "PromotionID": row_id,
                "Code": f"SAMPLE-PROMO-{row_id:05d}",
                "Title": f"Khuyen mai mau {row_id}",
                "DiscountType": "PERCENT" if row_id % 2 else "FIXED_AMOUNT",
                "DiscountValue": Decimal(5 if row_id % 2 else 50000),
                "MinOrderAmount": Decimal(100000),
                "MaxDiscountAmount": Decimal(200000),
                "UsageLimit": 100,
                "UsedCount": 0,
                "StartDate": now - timedelta(days=30),
                "EndDate": now + timedelta(days=30),
                "IsActive": 1,
            },
        )
        promotion_ids = _ids(connection, "Promotions", "PromotionID")

        _seed_role_permissions(connection, role_ids, permission_ids)

        _seed_rows(
            connection,
            "Products",
            "ProductID",
            lambda row_id: {
                "ProductID": row_id,
                "CategoryID": category_ids[row_id % len(category_ids)],
                "SupplierID": supplier_ids[row_id % len(supplier_ids)],
                "SKU": f"SAMPLE-SKU-{row_id:06d}",
                "Barcode": f"998{row_id:010d}",
                "ProductName": f"San pham mau tim kiem {row_id}",
                "MainImage": "/image/dell-inspiron-3020.jpg",
                "Specifications": f"Thong so san pham mau {row_id}",
                "CostPrice": Decimal(500000 + row_id * 10000),
                "SellingPrice": Decimal(650000 + row_id * 12000),
                "StockQuantity": 10 + row_id % 40,
                "WarrantyMonths": 12,
                "IsHasSerial": 1,
                "IsDeleted": 0,
            },
        )
        product_ids = _ids(connection, "Products", "ProductID")
        _seed_rows(
            connection,
            "Product_Images",
            "ImageID",
            lambda row_id: {
                "ImageID": row_id,
                "ProductID": product_ids[row_id % len(product_ids)],
                "ImageUrl": "/image/dell-inspiron-3020.jpg",
                "IsMain": 0,
                "SortOrder": row_id,
            },
        )

        _seed_rows(
            connection,
            "Inbound_Notes",
            "InboundID",
            lambda row_id: {
                "InboundID": row_id,
                "SupplierID": supplier_ids[row_id % len(supplier_ids)],
                "CreatedBy": user_ids[row_id % len(user_ids)],
                "ImportDate": now - timedelta(days=row_id),
                "TotalAmount": Decimal(1000000 + row_id * 50000),
                "Status": "COMPLETED",
                "Notes": "Phieu nhap du lieu mau",
            },
        )
        inbound_ids = _ids(connection, "Inbound_Notes", "InboundID")
        _seed_rows(
            connection,
            "Inbound_Details",
            "InboundDetailID",
            lambda row_id: {
                "InboundDetailID": row_id,
                "InboundID": inbound_ids[row_id % len(inbound_ids)],
                "ProductID": product_ids[row_id % len(product_ids)],
                "Quantity": 1 + row_id % 10,
                "ImportPrice": Decimal(500000 + row_id * 10000),
            },
        )
        inbound_detail_ids = _ids(connection, "Inbound_Details", "InboundDetailID")

        order_statuses = ("PENDING", "PAID", "SHIPPED", "COMPLETED")
        _seed_rows(
            connection,
            "Orders",
            "OrderID",
            lambda row_id: {
                "OrderID": row_id,
                "OrderCode": f"SAMPLE-ORDER-{row_id:06d}",
                "CustomerID": customer_ids[row_id % len(customer_ids)],
                "EmployeeID": user_ids[row_id % len(user_ids)],
                "PromotionID": promotion_ids[row_id % len(promotion_ids)],
                "SubTotal": Decimal(1000000 + row_id * 50000),
                "DiscountAmount": Decimal(50000),
                "TotalAmount": Decimal(950000 + row_id * 50000),
                "OrderStatus": order_statuses[row_id % len(order_statuses)],
                "OrderDate": now - timedelta(days=row_id),
                "Notes": "Don hang du lieu mau",
            },
        )
        order_ids = _ids(connection, "Orders", "OrderID")
        _seed_rows(
            connection,
            "Order_Details",
            "OrderDetailID",
            lambda row_id: {
                "OrderDetailID": row_id,
                "OrderID": order_ids[row_id % len(order_ids)],
                "ProductID": product_ids[row_id % len(product_ids)],
                "Quantity": 1 + row_id % 3,
                "UnitPrice": Decimal(750000 + row_id * 15000),
                "TotalPrice": Decimal((1 + row_id % 3) * (750000 + row_id * 15000)),
            },
        )
        order_detail_ids = _ids(connection, "Order_Details", "OrderDetailID")

        payment_methods = ("CASH", "BANK_TRANSFER", "CARD", "MOMO", "VNPAY")
        _seed_rows(
            connection,
            "Payments",
            "PaymentID",
            lambda row_id: {
                "PaymentID": row_id,
                "OrderID": order_ids[row_id % len(order_ids)],
                "Amount": Decimal(1000000 + row_id * 50000),
                "PaidAmount": Decimal(1000000 + row_id * 50000),
                "PaymentMethod": payment_methods[row_id % len(payment_methods)],
                "PaymentStatus": "PAID",
            },
        )
        payment_ids = _ids(connection, "Payments", "PaymentID")
        _seed_rows(
            connection,
            "Payment_Transactions",
            "TransactionID",
            lambda row_id: {
                "TransactionID": row_id,
                "PaymentID": payment_ids[row_id % len(payment_ids)],
                "TransCode": f"SAMPLE-TX-{row_id:06d}",
                "Amount": Decimal(1000000 + row_id * 50000),
                "PayGateway": "LOCAL_SAMPLE",
                "GatewayResponse": "Giao dich thanh toan mau",
                "Status": "SUCCESS",
                "TransactionTime": now - timedelta(days=row_id),
            },
        )

        _seed_rows(
            connection,
            "Product_Serials",
            "SerialID",
            lambda row_id: {
                "SerialID": row_id,
                "ProductID": product_ids[row_id % len(product_ids)],
                "SerialNumber": f"SAMPLE-SERIAL-{row_id:06d}",
                "Status": "AVAILABLE",
                "InboundDetailID": inbound_detail_ids[row_id % len(inbound_detail_ids)],
            },
        )
        _seed_rows(
            connection,
            "Warranties",
            "WarrantyID",
            lambda row_id: {
                "WarrantyID": row_id,
                "OrderDetailID": order_detail_ids[row_id % len(order_detail_ids)],
                "SerialNumber": f"SAMPLE-WARRANTY-{row_id:06d}",
                "StartDate": date.today() - timedelta(days=row_id),
                "EndDate": date.today() + timedelta(days=365),
                "Status": "ACTIVE",
            },
        )

        _seed_rows(
            connection,
            "User_Logs",
            "LogID",
            lambda row_id: {
                "LogID": row_id,
                "UserID": user_ids[row_id % len(user_ids)],
                "Action": "SAMPLE_ACTION",
                "Module": "SAMPLE",
                "IPAddress": "127.0.0.1",
                "UserAgent": "local-sample-data",
                "Description": "Nhat ky du lieu mau",
            },
        )
        _seed_rows(
            connection,
            "Customer_Login_Logs",
            "LoginLogID",
            lambda row_id: {
                "LoginLogID": row_id,
                "CustomerID": customer_ids[row_id % len(customer_ids)],
                "LoggedAt": now - timedelta(days=row_id),
                "IPAddress": "127.0.0.1",
                "UserAgent": "local-sample-data",
            },
        )
        _seed_rows(
            connection,
            "Customer_Addresses",
            "AddressID",
            lambda row_id: {
                "AddressID": row_id,
                "CustomerID": customer_ids[row_id % len(customer_ids)],
                "ReceiverName": f"Nguoi nhan mau {row_id}",
                "ReceiverPhone": f"098{row_id:08d}",
                "AddressDetail": f"So {row_id} Duong Mau",
                "ProvinceCity": "TP. Ho Chi Minh",
                "IsDefault": 1 if row_id % 10 == 0 else 0,
            },
        )
        _seed_rows(
            connection,
            "Password_Reset_Tokens",
            "PasswordResetID",
            lambda row_id: {
                "PasswordResetID": row_id,
                "CustomerID": customer_ids[row_id % len(customer_ids)],
                "TokenHash": hashlib.sha256(
                    f"expired-local-sample-token-{row_id}".encode("utf-8")
                ).hexdigest(),
                "ExpiresAt": now - timedelta(days=2),
                "UsedAt": now - timedelta(days=1),
                "FailedAttempts": 0,
            },
        )

        counts = {table: _count(connection, table) for table in TABLES}
        unexpected = {table: count for table, count in counts.items() if count < TARGET_ROWS}
        if unexpected:
            raise RuntimeError(f"Some tables are still below {TARGET_ROWS} rows: {unexpected}")


def main():
    _require_local_mysql()
    _ensure_search_indexes()
    seed_sample_data()

    with engine.connect() as connection:
        for table in TABLES:
            print(f"{table}: {_count(connection, table)}")


if __name__ == "__main__":
    main()
