import bcrypt
from flask import flash, request
from sqlalchemy import text

from controllers.admin.common import DashboardInputError, form_int, form_value


def handle_action(connection, action):
    if action in {"customer-create", "customer-update"}:
        customer_id = (
            form_int("id", minimum=1) if action == "customer-update" else None
        )
        values = {
            "id": customer_id,
            "username": form_value("username", required=True, maximum=50),
            "full_name": form_value("full_name", required=True, maximum=100),
            "phone": form_value("phone", required=True, maximum=20),
            "email": form_value("email", maximum=100) or None,
        }
        password = request.form.get("password", "")
        if action == "customer-create":
            if len(password) < 8 or len(password.encode("utf-8")) > 72:
                raise DashboardInputError(
                    "Mật khẩu cần từ 8 ký tự (tối đa 72 byte)."
                )
            connection.execute(
                text(
                    "INSERT INTO Customers "
                    "(Username, FullName, Phone, Email, PasswordHash) "
                    "VALUES (:username, :full_name, :phone, :email, :password_hash)"
                ),
                {
                    **values,
                    "password_hash": bcrypt.hashpw(
                        password.encode("utf-8"), bcrypt.gensalt()
                    ).decode("utf-8"),
                },
            )
            flash("Đã tạo khách hàng.", "success")
        elif password:
            if len(password) < 8 or len(password.encode("utf-8")) > 72:
                raise DashboardInputError(
                    "Mật khẩu cần từ 8 ký tự (tối đa 72 byte)."
                )
            connection.execute(
                text(
                    "UPDATE Customers SET Username=:username, FullName=:full_name, Phone=:phone, "
                    "Email=:email, PasswordHash=:password_hash "
                    "WHERE CustomerID=:id AND IsDeleted=0"
                ),
                {
                    **values,
                    "password_hash": bcrypt.hashpw(
                        password.encode("utf-8"), bcrypt.gensalt()
                    ).decode("utf-8"),
                },
            )
            flash("Đã cập nhật khách hàng và mật khẩu.", "success")
        else:
            connection.execute(
                text(
                    "UPDATE Customers SET Username=:username, FullName=:full_name, Phone=:phone, "
                    "Email=:email WHERE CustomerID=:id AND IsDeleted=0"
                ),
                values,
            )
            flash("Đã cập nhật khách hàng.", "success")
        return

    if action == "customer-delete":
        connection.execute(
            text(
                "UPDATE Customers SET IsDeleted=1, DeletedAt=CURRENT_TIMESTAMP "
                "WHERE CustomerID=:id AND IsDeleted=0"
            ),
            {"id": form_int("id", minimum=1)},
        )
        flash("Đã ẩn khách hàng.", "success")
        return

    raise ValueError(f"Unsupported customer action: {action}")
