import logging
import re

from flask import abort, render_template
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import engine

logger = logging.getLogger(__name__)


def _parse_specifications(specifications):
    rows = []
    for item in re.split(r",\s*|\r?\n", specifications or ""):
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
                    "SELECT p.ProductID, p.ProductName, p.SKU, p.Barcode, "
                    "p.MainImage, p.Specifications, p.SellingPrice, "
                    "p.StockQuantity, p.WarrantyMonths, c.CategoryName "
                    "FROM Products AS p "
                    "LEFT JOIN Categories AS c ON c.CategoryID = p.CategoryID "
                    "WHERE p.ProductID = :product_id AND p.IsDeleted = 0"
                ),
                {"product_id": product_id},
            ).mappings().first()
    except SQLAlchemyError:
        logger.exception("Không thể tải chi tiết sản phẩm %s", product_id)
        abort(503, description="Không thể tải chi tiết sản phẩm lúc này.")

    if product is None:
        abort(404)

    return render_template(
        "customer/product_detail.html",
        product=product,
        specification_rows=_parse_specifications(product["Specifications"]),
    )
