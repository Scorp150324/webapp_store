from flask import Blueprint

customer_bp = Blueprint("customer", __name__, url_prefix="/customer")

from controllers.customer.products import product_detail
from controllers.chat import customer_chat, customer_messages, customer_presence

customer_bp.add_url_rule(
    "/products/<int:product_id>",
    endpoint="product_detail",
    view_func=product_detail,
)
customer_bp.add_url_rule("/chat", endpoint="chat", view_func=customer_chat)
customer_bp.add_url_rule(
    "/presence",
    endpoint="presence",
    view_func=customer_presence,
    methods=["POST"],
)
customer_bp.add_url_rule(
    "/chat/messages",
    endpoint="chat_messages",
    view_func=customer_messages,
    methods=["GET", "POST"],
)
