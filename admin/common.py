import hmac
from decimal import Decimal, InvalidOperation

from flask import abort, request, session

MANAGER_ROLE_IDS = {1, 5}


class DashboardInputError(ValueError):
    pass


def form_value(name, *, required=False, maximum=None):
    value = request.form.get(name, "").strip()
    if required and not value:
        raise DashboardInputError(f"Trường {name} là bắt buộc.")
    if maximum is not None and len(value) > maximum:
        raise DashboardInputError(f"Trường {name} không được dài quá {maximum} ký tự.")
    return value


def form_int(name, *, minimum=None, optional=False):
    value = form_value(name)
    if not value and optional:
        return None
    try:
        result = int(value)
    except ValueError as error:
        raise DashboardInputError(f"Giá trị {name} không hợp lệ.") from error
    if minimum is not None and result < minimum:
        raise DashboardInputError(f"Giá trị {name} phải lớn hơn hoặc bằng {minimum}.")
    return result


def form_decimal(name, *, minimum=Decimal("0")):
    try:
        value = Decimal(form_value(name, required=True))
    except InvalidOperation as error:
        raise DashboardInputError(f"Giá trị {name} không hợp lệ.") from error
    if not value.is_finite() or value < minimum:
        raise DashboardInputError(f"Giá trị {name} không hợp lệ.")
    return value


def check_csrf_token():
    expected = session.get("dashboard_csrf_token", "")
    supplied = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        abort(400, description="Phiên biểu mẫu hết hạn. Hãy tải lại trang và thử lại.")
