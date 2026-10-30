import bcrypt
from flask import flash, request, session
from sqlalchemy import text

from controllers.admin.common import DashboardInputError, form_int, form_value


def handle_action(connection, action):
    if action == "employee-create":
        full_name = form_value("full_name", required=True, maximum=100)
        username = form_value("username", required=True, maximum=50)
        email = form_value("email", maximum=100) or None
        phone = form_value("phone", maximum=20) or None
        role_id = form_int("role_id", minimum=1)
        password = request.form.get("password", "")
        if len(password) < 8 or len(password.encode("utf-8")) > 72:
            raise DashboardInputError(
                "Mật khẩu nhân viên cần từ 8 ký tự (tối đa 72 byte)."
            )
        connection.execute(
            text(
                "INSERT INTO Users "
                "(RoleID, Username, PasswordHash, FullName, Email, Phone) "
                "VALUES (:role_id, :username, :password_hash, :full_name, :email, :phone)"
            ),
            {
                "role_id": role_id,
                "username": username,
                "password_hash": bcrypt.hashpw(
                    password.encode("utf-8"), bcrypt.gensalt()
                ).decode("utf-8"),
                "full_name": full_name,
                "email": email,
                "phone": phone,
            },
        )
        flash("Đã tạo tài khoản nhân viên.", "success")
        return

    if action == "employee-update":
        user_id = form_int("id", minimum=1)
        role_id = form_int("role_id", minimum=1)
        values = {
            "id": user_id,
            "role_id": role_id,
            "full_name": form_value("full_name", required=True, maximum=100),
            "email": form_value("email", maximum=100) or None,
            "phone": form_value("phone", maximum=20) or None,
        }
        password = request.form.get("password", "")
        if password:
            if len(password) < 8 or len(password.encode("utf-8")) > 72:
                raise DashboardInputError(
                    "Mật khẩu cần từ 8 ký tự (tối đa 72 byte)."
                )
            connection.execute(
                text(
                    "UPDATE Users SET RoleID=:role_id, FullName=:full_name, "
                    "Email=:email, Phone=:phone, PasswordHash=:password_hash "
                    "WHERE UserID=:id AND IsDeleted=0"
                ),
                {
                    **values,
                    "password_hash": bcrypt.hashpw(
                        password.encode("utf-8"), bcrypt.gensalt()
                    ).decode("utf-8"),
                },
            )
        else:
            connection.execute(
                text(
                    "UPDATE Users SET RoleID=:role_id, FullName=:full_name, "
                    "Email=:email, Phone=:phone WHERE UserID=:id AND IsDeleted=0"
                ),
                values,
            )
        flash("Đã cập nhật tài khoản nhân viên.", "success")
        return

    if action == "employee-delete":
        user_id = form_int("id", minimum=1)
        if user_id == session.get("user_id"):
            raise DashboardInputError("Không thể tự khóa tài khoản đang sử dụng.")
        connection.execute(
            text(
                "UPDATE Users SET IsDeleted=1, DeletedAt=CURRENT_TIMESTAMP "
                "WHERE UserID=:id AND IsDeleted=0"
            ),
            {"id": user_id},
        )
        flash("Đã khóa tài khoản nhân viên.", "success")
        return

    raise ValueError(f"Unsupported employee action: {action}")
