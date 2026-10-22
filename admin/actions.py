import logging

from flask import abort, flash, redirect, session, url_for
from sqlalchemy.exc import IntegrityError

from admin.common import DashboardInputError
from admin.customers import handle_action as handle_customer_action
from admin.employees import handle_action as handle_employee_action
from admin.inventory import handle_action as handle_inventory_action
from admin.products import handle_action as handle_product_action
from database import engine

logger = logging.getLogger(__name__)

ACTION_HANDLERS = {
    "employee-create": handle_employee_action,
    "employee-update": handle_employee_action,
    "employee-delete": handle_employee_action,
    "customer-create": handle_customer_action,
    "customer-update": handle_customer_action,
    "customer-delete": handle_customer_action,
    "product-create": handle_product_action,
    "product-update": handle_product_action,
    "product-delete": handle_product_action,
    "product-restore": handle_product_action,
    "inbound-create": handle_inventory_action,
    "outbound-create": handle_inventory_action,
}


def action(action):
    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        abort(404)
    if action.startswith("employee-") and session.get("role_id") != 1:
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

    return redirect(url_for("dashboard.home") + f"#{action.split('-')[0]}-section")
