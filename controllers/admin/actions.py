import logging

from flask import abort, flash, redirect, session, url_for
from sqlalchemy.exc import IntegrityError

from controllers.admin.common import DashboardInputError
from controllers.admin.categories import handle_action as handle_category_action
from controllers.admin.customers import handle_action as handle_customer_action
from controllers.admin.employees import handle_action as handle_employee_action
from controllers.admin.inventory import handle_action as handle_inventory_action
from controllers.admin.products import handle_action as handle_product_action
from controllers.admin.roles import handle_action as handle_role_action
from database import engine

logger = logging.getLogger(__name__)

ACTION_HANDLERS = {
    "category-create": handle_category_action,
    "category-update": handle_category_action,
    "category-delete": handle_category_action,
    "employee-create": handle_employee_action,
    "employee-update": handle_employee_action,
    "employee-delete": handle_employee_action,
    "employee-restore": handle_employee_action,
    "role-create": handle_role_action,
    "role-update": handle_role_action,
    "role-delete": handle_role_action,
    "customer-create": handle_customer_action,
    "customer-update": handle_customer_action,
    "customer-delete": handle_customer_action,
    "customer-restore": handle_customer_action,
    "product-create": handle_product_action,
    "product-update": handle_product_action,
    "product-delete": handle_product_action,
    "product-restore": handle_product_action,
    "inbound-create": handle_inventory_action,
    "inbound-update": handle_inventory_action,
    "inbound-delete": handle_inventory_action,
    "inbound-restore": handle_inventory_action,
    "outbound-create": handle_inventory_action,
    "outbound-update": handle_inventory_action,
    "outbound-delete": handle_inventory_action,
    "outbound-restore": handle_inventory_action,
}


def action(action):
    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        abort(404)
    if action.startswith("employee-") and session.get("role_id") != 1:
        abort(403)
    if action.startswith("role-") and session.get("role_id") != 1:
        abort(403)
    if action.startswith("category-") and session.get("role_id") != 1:
        abort(403)
    if action == "customer-restore" and session.get("role_id") != 1:
        abort(403)

    try:
        with engine.begin() as connection:
            handler(connection, action)
    except DashboardInputError as error:
        flash(str(error), "error")
    except IntegrityError:
        logger.exception("Vi phạm ràng buộc khi quản lý dashboard")
        flash("Dữ liệu trùng lặp hoặc tham chiếu không hợp lệ.", "error")
    except Exception:
        logger.exception("Không thể hoàn tất thao tác dashboard: %s", action)
        flash("Không thể hoàn tất thao tác. Kiểm tra cơ sở dữ liệu và thử lại.", "error")

    section = (
        "inbound-section"
        if action.startswith("inbound-")
        else "outbound-section"
        if action.startswith("outbound-")
        else "roles-section"
        if action.startswith("role-")
        else "categories-section"
        if action.startswith("category-")
        else f"{action.split('-')[0]}-section"
    )
    return redirect(url_for("dashboard.home") + f"#{section}")
