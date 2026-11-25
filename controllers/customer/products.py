import logging
import re

from flask import abort, render_template
from sqlalchemy.exc import SQLAlchemyError

from controllers.contact import get_admin_contact
from database import engine, text

logger = logging.getLogger(__name__)


def _parse_specifications(specifications):
    rows = []
    # Specifications use semicolons (or line breaks) as separators. Do not
    # split on commas because commas may be part of a specification value.
    for item in re.split(r";\s*|\r?\n", specifications or ""):
        item = item.strip()
        if not item:
            continue

        label, separator, value = item.partition(":")
        if separator:
            rows.append({"label": label.strip(), "value": value.strip()})
        else:
            rows.append({"label": "Thông tin khác", "value": item})
    return rows


def product_detail(product_id):
    try:
        with engine.connect() as connection:
            product = connection.execute(
                text(
                    "SELECT p.ProductID, p.ProductName, "
                    "p.MainImage, p.Specifications, p.SellingPrice, "
                    "p.StockQuantity, p.WarrantyMonths, "
                    "c.CategoryName "
                    "FROM Products AS p "
                    "LEFT JOIN Categories AS c ON c.CategoryID = p.CategoryID "
                    "WHERE p.ProductID = :product_id AND p.IsDeleted = 0"
                ),
                {"product_id": product_id},
            ).mappings().first()
            if product is not None:
                image_rows = connection.execute(
                    text(
                        "SELECT ImageUrl FROM Product_Images "
                        "WHERE ProductID = :product_id "
                        "ORDER BY IsMain DESC, SortOrder ASC, ImageID ASC"
                    ),
                    {"product_id": product_id},
                ).mappings().all()
                admin_contact = get_admin_contact(connection)
            else:
                image_rows = []
                admin_contact = None
    except SQLAlchemyError:
        logger.exception("Không thể tải chi tiết sản phẩm %s", product_id)
        abort(503, description="Không thể tải chi tiết sản phẩm lúc này.")

    if product is None:
        abort(404)

    product_images = []
    for image_url in [product["MainImage"]] + [
        row["ImageUrl"] for row in image_rows
    ]:
        if image_url and image_url not in product_images:
            product_images.append(image_url)

    return render_template(
        "customer/product_detail.html",
        product=product,
        product_images=product_images,
        admin_contact=admin_contact,
        specification_rows=_parse_specifications(product["Specifications"]),
    )
