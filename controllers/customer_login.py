import logging
import time

import bcrypt

from database import engine, text

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 6
LOCK_DURATIONS_SECONDS = (10, 30, 60)


def _managed_lock():
    return {"admin_locked": True, "managed_locked": True}


def authenticate_customer(identity, password):
    """Authenticate customers and apply one challenge attempt per lock stage."""
    with engine.connect() as connection:
        customer = connection.execute(
            text(
                "SELECT CustomerID, FullName, PasswordHash, IsDeleted, "
                "LoginFailedAttempts, LoginLockLevel, LoginLockedUntil "
                "FROM Customers WHERE (Username = :identity OR Phone = :identity "
                "OR Email = :identity) AND (IsDeleted = 1 OR PasswordHash IS NOT NULL)"
            ),
            {"identity": identity},
        ).mappings().first()

    if not customer:
        return None, None
    if customer["IsDeleted"]:
        return customer, _managed_lock()

    now = int(time.time())
    locked_until = int(customer["LoginLockedUntil"] or 0)
    if locked_until > now:
        return customer, {"remaining": locked_until - now}

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
        with engine.begin() as connection:
            latest = connection.execute(
                text(
                    "SELECT IsDeleted FROM Customers WHERE CustomerID=:customer_id "
                    "FOR UPDATE"
                ),
                {"customer_id": customer["CustomerID"]},
            ).mappings().first()
            if latest["IsDeleted"]:
                return customer, _managed_lock()
            connection.execute(
                text(
                    "UPDATE Customers SET LoginFailedAttempts=0, LoginLockLevel=0, "
                    "LoginLockedUntil=0 WHERE CustomerID=:customer_id"
                ),
                {"customer_id": customer["CustomerID"]},
            )
        return customer, None

    with engine.begin() as connection:
        latest = connection.execute(
            text(
                "SELECT IsDeleted, LoginFailedAttempts, LoginLockLevel, LoginLockedUntil "
                "FROM Customers WHERE CustomerID=:customer_id FOR UPDATE"
            ),
            {"customer_id": customer["CustomerID"]},
        ).mappings().first()
        if latest["IsDeleted"]:
            return customer, _managed_lock()

        now = int(time.time())
        locked_until = int(latest["LoginLockedUntil"] or 0)
        if locked_until > now:
            return customer, {"remaining": locked_until - now}

        lock_level = int(latest["LoginLockLevel"] or 0)
        if lock_level == 0:
            attempts = int(latest["LoginFailedAttempts"] or 0) + 1
            if attempts < MAX_FAILED_ATTEMPTS:
                connection.execute(
                    text(
                        "UPDATE Customers SET LoginFailedAttempts=:attempts "
                        "WHERE CustomerID=:customer_id"
                    ),
                    {"attempts": attempts, "customer_id": customer["CustomerID"]},
                )
                return customer, {"failed": True}
            lock_level = 1
        else:
            # After each cooldown, one wrong password advances to the next stage.
            lock_level += 1
            if lock_level > len(LOCK_DURATIONS_SECONDS):
                connection.execute(
                    text(
                        "UPDATE Customers SET IsDeleted=1, DeletedAt=CURRENT_TIMESTAMP, "
                        "LoginFailedAttempts=0, LoginLockedUntil=0 "
                        "WHERE CustomerID=:customer_id"
                    ),
                    {"customer_id": customer["CustomerID"]},
                )
                return customer, _managed_lock()

        duration = LOCK_DURATIONS_SECONDS[lock_level - 1]
        locked_until = now + duration
        connection.execute(
            text(
                "UPDATE Customers SET LoginFailedAttempts=0, LoginLockLevel=:lock_level, "
                "LoginLockedUntil=:locked_until WHERE CustomerID=:customer_id"
            ),
            {
                "lock_level": lock_level,
                "locked_until": locked_until,
                "customer_id": customer["CustomerID"],
            },
        )

    return customer, {"remaining": duration}


def customer_lock_message(lock_info):
    if not lock_info or lock_info.get("failed"):
        return None
    if lock_info.get("managed_locked"):
        return "Tài khoản này đã bị khóa. Vui lòng liên hệ admin để được hỗ trợ mở khóa."
    remaining = int(lock_info.get("remaining", 0))
    if remaining:
        return f"Tài khoản đang bị khóa. Vui lòng thử lại sau {remaining} giây."
    return None
