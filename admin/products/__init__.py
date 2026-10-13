from flask import flash, request
from sqlalchemy import text

from admin.common import form_decimal, form_int, form_value


def handle_action(connection, action):
    if action in {"product-create", "product-update"}:
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
            flash(
                "Đã tạo sản phẩm. Tồn kho ban đầu là 0; dùng phiếu nhập để bổ sung hàng.",
                "success",
            )
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
        return

    if action == "product-delete":
        connection.execute(
            text(
                "UPDATE Products SET IsDeleted=1, DeletedAt=CURRENT_TIMESTAMP "
                "WHERE ProductID=:id AND IsDeleted=0"
            ),
            {"id": form_int("id", minimum=1)},
        )
        flash("Đã ẩn sản phẩm.", "success")
        return

    raise ValueError(f"Unsupported product action: {action}")
