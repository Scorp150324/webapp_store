import logging

import bcrypt

from database import engine, text

logger = logging.getLogger(__name__)


def authenticate_customer(identity, password):
    """Authenticate an active customer and report the dashboard soft lock."""
    with engine.connect() as connection:
        customer = connection.execute(
            text(
                "SELECT CustomerID, FullName, PasswordHash, IsDeleted "
                "FROM Customers WHERE (Username = :identity OR Phone = :identity "
                "OR Email = :identity) AND (IsDeleted = 1 OR PasswordHash IS NOT NULL)"
            ),
            {"identity": identity},
        ).mappings().first()

    if not customer:
        return None, None

    if customer["IsDeleted"]:
        return customer, {"admin_locked": True, "managed_locked": True}

    try:
        password_matches = bcrypt.checkpw(
            password.encode("utf-8"), customer["PasswordHash"].encode("utf-8")
        )
    except (ValueError, TypeError, AttributeError):
        logger.exception(
            "Invalid customer password hash (CustomerID=%s)", customer["CustomerID"]
        )
        password_matches = False

    if password_matches:
        return customer, None
    return customer, {"failed": True}


def customer_lock_message(lock_info):
    if lock_info and lock_info.get("managed_locked"):
        return "Tài khoản này đã bị khóa. Vui lòng liên hệ quản lý để được hỗ trợ."
    return None
