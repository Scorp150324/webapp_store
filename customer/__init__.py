from flask import Blueprint, abort, flash, redirect, session, url_for

customer_bp = Blueprint("customer", __name__, url_prefix="/customer")


@customer_bp.before_request
def require_customer_login():
    if session.get("user_type") != "customer":
        if session.get("user_id"):
            abort(403)
        flash("Vui lòng đăng nhập tài khoản khách hàng để xem chi tiết sản phẩm.", "error")
        return redirect(url_for("login"))


from customer.products import product_detail

customer_bp.add_url_rule(
    "/products/<int:product_id>",
    endpoint="product_detail",
    view_func=product_detail,
)
