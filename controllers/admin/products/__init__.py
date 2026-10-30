import os
import secrets
from urllib.parse import urlsplit

from flask import flash, request
from werkzeug.utils import secure_filename
from sqlalchemy import text

from controllers.admin.common import DashboardInputError, form_decimal, form_int, form_value

IMAGE_UPLOAD_FOLDER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "image"
)
ALLOWED_IMAGE_EXTENSIONS = {"gif", "jpeg", "jpg", "png", "webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


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
        image_url = values["main_image"]
        if image_url and not image_url.startswith("/image/"):
            parsed_url = urlsplit(image_url)
            if not parsed_url.scheme or not parsed_url.netloc:
                raise DashboardInputError("URL ảnh không hợp lệ.")

        image = request.files.get("main_image_file")
        if image and image.filename:
            filename = secure_filename(image.filename)
            extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if extension not in ALLOWED_IMAGE_EXTENSIONS:
                raise DashboardInputError("Định dạng ảnh không được hỗ trợ.")
            image.stream.seek(0, os.SEEK_END)
            image_size = image.stream.tell()
            image.stream.seek(0)
            if image_size > MAX_IMAGE_SIZE:
                raise DashboardInputError("Ảnh không được lớn hơn 5 MB.")

            stored_filename = f"{secrets.token_hex(16)}.{extension}"
            os.makedirs(IMAGE_UPLOAD_FOLDER, exist_ok=True)
            image.save(os.path.join(IMAGE_UPLOAD_FOLDER, stored_filename))
            values["main_image"] = f"/image/{stored_filename}"

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

    if action == "product-restore":
        connection.execute(
            text(
                "UPDATE Products SET IsDeleted=0, DeletedAt=NULL "
                "WHERE ProductID=:id AND IsDeleted=1"
            ),
            {"id": form_int("id", minimum=1)},
        )
        flash("Đã khôi phục sản phẩm. Sản phẩm đã xuất hiện lại trên cửa hàng.", "success")
        return

    raise ValueError(f"Unsupported product action: {action}")
