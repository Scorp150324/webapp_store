from database import text


def get_admin_contact(connection):
    row = connection.execute(
        text(
            "SELECT u.Email, u.Phone "
            "FROM Users AS u "
            "WHERE u.RoleID = :role_id AND u.IsDeleted = 0 "
            "AND ((u.Phone IS NOT NULL AND TRIM(u.Phone) <> '') "
            "OR (u.Email IS NOT NULL AND TRIM(u.Email) <> '' "
            "AND LOWER(u.Email) NOT LIKE '%@example.invalid')) "
            "ORDER BY u.UserID ASC LIMIT 1"
        ),
        {"role_id": 1},
    ).mappings().first()
    if row is None:
        return None

    email = (row["Email"] or "").strip()
    if email.casefold().endswith("@example.invalid"):
        email = ""
    phone = (row["Phone"] or "").strip()
    phone_digits = "".join(character for character in phone if character.isdigit())
    phone_href = f"+{phone_digits}" if phone.lstrip().startswith("+") else phone_digits
    if not phone_digits:
        phone = ""

    if not email and not phone:
        return None
    return {
        "email": email or None,
        "phone": phone or None,
        "phone_href": phone_href or None,
    }
