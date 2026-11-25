from flask import Blueprint

customer_bp = Blueprint("customer", __name__, url_prefix="/customer")

from controllers.customer.products import product_detail

customer_bp.add_url_rule(
    "/products/<int:product_id>",
    endpoint="product_detail",
    view_func=product_detail,
)
