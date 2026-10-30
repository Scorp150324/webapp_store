from flask import Blueprint, abort, request, session

from controllers.admin.common import MANAGER_ROLE_IDS, check_csrf_token

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.before_request
def guard_dashboard():
    if (
        session.get("user_type") != "staff"
        or session.get("role_id") not in MANAGER_ROLE_IDS
    ):
        abort(403)
    if request.method == "POST":
        check_csrf_token()


from controllers.admin.actions import action
from controllers.admin.overview import home

dashboard_bp.add_url_rule("/dashboard", endpoint="home", view_func=home)
dashboard_bp.add_url_rule(
    "/dashboard/action/<action>",
    endpoint="action",
    view_func=action,
    methods=["POST"],
)
