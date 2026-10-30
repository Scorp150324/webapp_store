from decimal import Decimal

from flask import abort, jsonify, request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api import api_bp
from database import engine


def _serialize_product(row):
    product = dict(row)
    price = product.get("SellingPrice")
    if isinstance(price, Decimal):
        product["SellingPrice"] = float(price)
    return product


@api_bp.get("/products")
def list_products():
    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "20"))
    except ValueError:
        abort(400, description="page và per_page phải là số nguyên.")
    if page < 1 or per_page < 1 or per_page > 100:
        abort(400, description="page phải từ 1; per_page phải từ 1 đến 100.")

    search = request.args.get("q", "").strip()[:100]
    where_clause = "WHERE p.IsDeleted = 0"
    parameters = {"limit": per_page, "offset": (page - 1) * per_page}
    if search:
        where_clause += (
            " AND (p.ProductName LIKE :search OR p.SKU LIKE :search "
            "OR p.Barcode LIKE :search OR p.Specifications LIKE :search)"
        )
        parameters["search"] = f"%{search}%"

    try:
        with engine.connect() as connection:
            total = connection.execute(
                text(
                    "SELECT COUNT(*) FROM Products AS p "
                    f"{where_clause}"
                ),
                parameters,
            ).scalar_one()
            rows = connection.execute(
                text(
                    "SELECT p.ProductID, p.ProductName, p.SKU, p.Barcode, "
                    "p.MainImage, p.SellingPrice, p.StockQuantity, "
                    "c.CategoryName "
                    "FROM Products AS p "
                    "LEFT JOIN Categories AS c ON c.CategoryID = p.CategoryID "
                    f"{where_clause} "
                    "ORDER BY p.ProductID DESC LIMIT :limit OFFSET :offset"
                ),
                parameters,
            ).mappings().all()
    except SQLAlchemyError:
        abort(503, description="Không thể tải danh sách sản phẩm lúc này.")

    return jsonify(
        data=[_serialize_product(row) for row in rows],
        pagination={
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        },
    )


@api_bp.get("/products/<int:product_id>")
def get_product(product_id):
    try:
        with engine.connect() as connection:
            product = connection.execute(
                text(
                    "SELECT p.ProductID, p.ProductName, p.SKU, p.Barcode, "
                    "p.MainImage, p.Specifications, p.SellingPrice, "
                    "p.StockQuantity, c.CategoryName "
                    "FROM Products AS p "
                    "LEFT JOIN Categories AS c ON c.CategoryID = p.CategoryID "
                    "WHERE p.ProductID = :product_id AND p.IsDeleted = 0"
                ),
                {"product_id": product_id},
            ).mappings().first()
            if product is None:
                abort(404, description="Không tìm thấy sản phẩm.")
            image_rows = connection.execute(
                text(
                    "SELECT ImageUrl FROM Product_Images "
                    "WHERE ProductID = :product_id "
                    "ORDER BY IsMain DESC, SortOrder ASC, ImageID ASC"
                ),
                {"product_id": product_id},
            ).mappings().all()
    except SQLAlchemyError:
        abort(503, description="Không thể tải chi tiết sản phẩm lúc này.")

    serialized = _serialize_product(product)
    serialized["images"] = [
        row["ImageUrl"] for row in image_rows if row["ImageUrl"]
    ]
    return jsonify(data=serialized)
