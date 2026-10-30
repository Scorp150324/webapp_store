import hmac
import logging
import secrets

import bcrypt
from flask import abort, jsonify, request, session
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api import api_bp
from database import engine

logger = logging.getLogger(__name__)


def _require_csrf_token():
    expected = session.get("api_csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        abort(400, description="CSRF token không hợp lệ hoặc đã hết hạn.")


@api_bp.get("/auth/csrf-token")
def get_csrf_token():
    token = session.setdefault("api_csrf_token", secrets.token_urlsafe(32))
    return jsonify(csrf_token=token)


@api_bp.post("/auth/login")
def api_login():
    if not request.is_json:
        abort(415, description="Yêu cầu gửi dữ liệu JSON.")
    _require_csrf_token()
    payload = request.get_json()
    identity = payload.get("identity", "") if isinstance(payload, dict) else ""
    password = payload.get("password", "") if isinstance(payload, dict) else ""
    if not isinstance(identity, str) or not isinstance(password, str):
        abort(400, description="identity và password phải là chuỗi.")
    identity = identity.strip()
    if not identity or not password or len(identity) > 100:
        abort(400, description="Vui lòng cung cấp identity và password hợp lệ.")

    try:
        with engine.connect() as connection:
            customer = connection.execute(
                text(
                    "SELECT CustomerID, FullName, PasswordHash "
                    "FROM Customers "
                    "WHERE (Username = :identity OR Phone = :identity "
                    "OR Email = :identity) AND IsDeleted = 0 "
                    "AND PasswordHash IS NOT NULL"
                ),
                {"identity": identity},
            ).mappings().first()
            if customer:
                try:
                    valid_password = bcrypt.checkpw(
                        password.encode("utf-8"),
                        customer["PasswordHash"].encode("utf-8"),
                    )
                except ValueError:
                    logger.exception(
                        "Hash mật khẩu khách hàng không hợp lệ (CustomerID=%s)",
                        customer["CustomerID"],
                    )
                    valid_password = False
                if valid_password:
                    try:
                        with engine.begin() as log_connection:
                            log_connection.execute(
                                text(
                                    "INSERT INTO Customer_Login_Logs "
                                    "(CustomerID, IPAddress, UserAgent) "
                                    "VALUES (:customer_id, :ip_address, :user_agent)"
                                ),
                                {
                                    "customer_id": customer["CustomerID"],
                                    "ip_address": request.remote_addr,
                                    "user_agent": request.user_agent.string[:255],
                                },
                            )
                    except SQLAlchemyError:
                        logger.exception("Không thể ghi nhật ký đăng nhập khách hàng")
                    account = {
                        "id": customer["CustomerID"],
                        "type": "customer",
                        "full_name": customer["FullName"],
                    }
                else:
                    account = None
            else:
                account = None

            if account is None:
                user = connection.execute(
                    text(
                        "SELECT UserID, Username, PasswordHash, FullName, RoleID "
                        "FROM Users WHERE (Username = :identity OR Email = :identity "
                        "OR Phone = :identity) AND IsDeleted = 0"
                    ),
                    {"identity": identity},
                ).mappings().first()
                if user:
                    try:
                        valid_password = bcrypt.checkpw(
                            password.encode("utf-8"),
                            user["PasswordHash"].encode("utf-8"),
                        )
                    except ValueError:
                        logger.exception(
                            "Hash mật khẩu nhân viên không hợp lệ (UserID=%s)",
                            user["UserID"],
                        )
                        valid_password = False
                    if valid_password:
                        account = {
                            "id": user["UserID"],
                            "type": "staff",
                            "full_name": user["FullName"],
                            "username": user["Username"],
                            "role_id": user["RoleID"],
                        }
    except SQLAlchemyError:
        abort(503, description="Không thể kết nối cơ sở dữ liệu lúc này.")

    if account is None:
        abort(401, description="Thông tin đăng nhập không đúng.")

    session.clear()
    session["user_id"] = account["id"]
    session["user_type"] = account["type"]
    session["full_name"] = account["full_name"]
    if account["type"] == "staff":
        session["username"] = account["username"]
        session["role_id"] = account["role_id"]
    csrf_token = secrets.token_urlsafe(32)
    session["api_csrf_token"] = csrf_token
    return jsonify(data=account, csrf_token=csrf_token)


@api_bp.post("/auth/logout")
def api_logout():
    _require_csrf_token()
    if not session.get("user_id"):
        abort(401, description="Bạn chưa đăng nhập.")
    session.clear()
    return jsonify(message="Đã đăng xuất.")
