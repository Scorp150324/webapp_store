from flask import flash

from controllers.admin.common import DashboardInputError, form_int, form_value
from database import text


def _get_category(connection, category_id, *, lock=False):
    statement = (
        "SELECT CategoryID, CategoryName, ParentID, Description "
        "FROM Categories WHERE CategoryID=:id"
    )
    if lock:
        statement += " FOR UPDATE"
    category = connection.execute(text(statement), {"id": category_id}).mappings().first()
    if category is None:
        raise DashboardInputError("Danh mục không tồn tại hoặc đã bị xóa.")
    return category


def _validate_parent(connection, category_id, parent_id):
    if parent_id is None:
        return
    if category_id == parent_id:
        raise DashboardInputError("Danh mục không thể là danh mục cha của chính nó.")

    current_id = parent_id
    visited = set()
    while current_id is not None:
        if current_id in visited:
            raise DashboardInputError("Cấu trúc danh mục không hợp lệ.")
        visited.add(current_id)
        if current_id == category_id:
            raise DashboardInputError("Không thể chọn danh mục con làm danh mục cha.")
        parent = connection.execute(
            text("SELECT ParentID FROM Categories WHERE CategoryID=:id"),
            {"id": current_id},
        ).mappings().first()
        if parent is None:
            raise DashboardInputError("Danh mục cha không tồn tại.")
        current_id = parent["ParentID"]


def _category_values(connection, *, exclude_id=None):
    name = form_value("category_name", required=True, maximum=100)
    description = form_value("description", maximum=255) or None
    parent_id = form_int("parent_id", minimum=1, optional=True)

    duplicate = connection.execute(
        text(
            "SELECT CategoryID FROM Categories "
            "WHERE LOWER(CategoryName)=LOWER(:name) "
            "AND (:exclude_id IS NULL OR CategoryID<>:exclude_id) LIMIT 1"
        ),
        {"name": name, "exclude_id": exclude_id},
    ).first()
    if duplicate:
        raise DashboardInputError("Tên danh mục này đã được sử dụng.")

    _validate_parent(connection, exclude_id, parent_id)
    return name, description, parent_id


def handle_action(connection, action):
    if action == "category-create":
        name, description, parent_id = _category_values(connection)
        connection.execute(
            text(
                "INSERT INTO Categories (CategoryName, ParentID, Description) "
                "VALUES (:name, :parent_id, :description)"
            ),
            {"name": name, "parent_id": parent_id, "description": description},
        )
        flash("Đã thêm danh mục.", "success")
        return

    if action == "category-update":
        category_id = form_int("id", minimum=1)
        _get_category(connection, category_id, lock=True)
        name, description, parent_id = _category_values(
            connection, exclude_id=category_id
        )
        connection.execute(
            text(
                "UPDATE Categories SET CategoryName=:name, ParentID=:parent_id, "
                "Description=:description WHERE CategoryID=:id"
            ),
            {
                "id": category_id,
                "name": name,
                "parent_id": parent_id,
                "description": description,
            },
        )
        flash("Đã cập nhật danh mục.", "success")
        return

    if action == "category-delete":
        category_id = form_int("id", minimum=1)
        _get_category(connection, category_id, lock=True)
        product_count = connection.execute(
            text("SELECT COUNT(*) FROM Products WHERE CategoryID=:id"),
            {"id": category_id},
        ).scalar_one()
        if product_count:
            raise DashboardInputError(
                "Không thể xóa danh mục đang được dùng cho sản phẩm. "
                "Hãy chuyển sản phẩm sang danh mục khác trước."
            )
        child_count = connection.execute(
            text("SELECT COUNT(*) FROM Categories WHERE ParentID=:id"),
            {"id": category_id},
        ).scalar_one()
        if child_count:
            raise DashboardInputError(
                "Không thể xóa danh mục đang có danh mục con. "
                "Hãy chuyển hoặc xóa các danh mục con trước."
            )
        connection.execute(
            text("DELETE FROM Categories WHERE CategoryID=:id"), {"id": category_id}
        )
        flash("Đã xóa danh mục.", "success")
        return

    raise ValueError(f"Unsupported category action: {action}")
