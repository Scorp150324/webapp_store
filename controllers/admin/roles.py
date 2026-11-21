from flask import flash, request

from controllers.admin.common import DashboardInputError, form_int, form_value
from database import text


def _get_role(connection, role_id, *, lock=False):
    statement = "SELECT RoleID, RoleName, Description FROM Roles WHERE RoleID=:id"
    if lock:
        statement += " FOR UPDATE"
    role = connection.execute(text(statement), {"id": role_id}).mappings().first()
    if role is None:
        raise DashboardInputError("Vai trò không tồn tại hoặc đã bị xóa.")
    return role


def _role_values(connection, *, exclude_id=None, current_role=None):
    role_name = form_value("role_name", required=True, maximum=50)
    description = form_value("description", maximum=255) or None

    if role_name.casefold() == "admin" and (
        current_role is None or current_role["RoleID"] != 1
    ):
        raise DashboardInputError("Tên ADMIN được dành riêng cho vai trò quản trị hệ thống.")

    existing = connection.execute(
        text(
            "SELECT RoleID FROM Roles WHERE LOWER(RoleName)=LOWER(:role_name) "
            "AND (:exclude_id IS NULL OR RoleID<>:exclude_id) LIMIT 1"
        ),
        {"role_name": role_name, "exclude_id": exclude_id},
    ).first()
    if existing:
        raise DashboardInputError("Tên vai trò này đã được sử dụng.")

    if current_role and current_role["RoleID"] == 1 and role_name != current_role["RoleName"]:
        raise DashboardInputError("Không thể đổi tên vai trò ADMIN.")

    return role_name, description


def handle_action(connection, action):
    if action == "role-create":
        role_name, description = _role_values(connection)
        connection.execute(
            text("INSERT INTO Roles (RoleName, Description) VALUES (:name, :description)"),
            {"name": role_name, "description": description},
        )
        flash("Đã thêm vai trò.", "success")
        return

    if action == "role-update":
        role_id = form_int("id", minimum=1)
        current_role = _get_role(connection, role_id, lock=True)
        role_name, description = _role_values(
            connection, exclude_id=role_id, current_role=current_role
        )
        connection.execute(
            text("UPDATE Roles SET RoleName=:name, Description=:description WHERE RoleID=:id"),
            {"id": role_id, "name": role_name, "description": description},
        )
        flash("Đã cập nhật vai trò.", "success")
        return

    if action == "role-delete":
        role_id = form_int("id", minimum=1)
        role = _get_role(connection, role_id, lock=True)
        if role_id == 1 or role["RoleName"].strip().casefold() == "admin":
            raise DashboardInputError("Không thể xóa vai trò ADMIN.")

        assigned_count = connection.execute(
            text("SELECT COUNT(*) FROM Users WHERE RoleID=:id"), {"id": role_id}
        ).scalar_one()
        if assigned_count:
            raise DashboardInputError(
                "Vai trò đang được gán cho nhân viên. Hãy chuyển nhân viên sang vai trò khác trước."
            )

        connection.execute(text("DELETE FROM Roles WHERE RoleID=:id"), {"id": role_id})
        flash("Đã xóa vai trò.", "success")
        return

    raise ValueError(f"Unsupported role action: {action}")
