import logging
import secrets

from flask import abort, jsonify, render_template, request, session

from database import engine, insert_id, text

logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 2000


def _require_customer():
    if session.get("user_type") != "customer" or not session.get("user_id"):
        abort(403)
    return int(session["user_id"])


def _require_staff():
    if session.get("user_type") != "staff" or session.get("role_id") not in {1, 5}:
        abort(403)
    return int(session["user_id"])


def _check_chat_csrf():
    expected = session.get("chat_csrf_token", "")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    if not expected or supplied != expected:
        abort(400, description="Phiên chat hết hạn. Hãy tải lại trang và thử lại.")


def _chat_token():
    return session.setdefault("chat_csrf_token", secrets.token_urlsafe(32))


def _ensure_conversation(connection, customer_id):
    conversation = connection.execute(
        text(
            "SELECT ConversationID FROM Chat_Conversations "
            "WHERE CustomerID=:customer_id"
        ),
        {"customer_id": customer_id},
    ).mappings().first()
    if conversation:
        return conversation["ConversationID"]
    return insert_id(
        connection,
        "INSERT INTO Chat_Conversations (CustomerID) VALUES (:customer_id)",
        {"customer_id": customer_id},
        "ConversationID",
    )


def _messages(connection, conversation_id, *, mark_customer_read=None, mark_staff_read=False):
    if mark_customer_read is not None:
        connection.execute(
            text(
                "UPDATE Chat_Messages SET IsRead=1 "
                "WHERE ConversationID=:conversation_id AND SenderType='STAFF'"
            ),
            {"conversation_id": conversation_id},
        )
    elif mark_staff_read:
        connection.execute(
            text(
                "UPDATE Chat_Messages SET IsRead=1 "
                "WHERE ConversationID=:conversation_id AND SenderType='CUSTOMER'"
            ),
            {"conversation_id": conversation_id},
        )
    return connection.execute(
        text(
            "SELECT m.MessageID, m.SenderType, m.MessageText, m.CreatedAt, "
            "COALESCE(u.FullName, c.FullName) AS SenderName "
            "FROM Chat_Messages AS m "
            "LEFT JOIN Users AS u ON u.UserID=m.SenderUserID "
            "LEFT JOIN Customers AS c ON c.CustomerID=m.SenderCustomerID "
            "WHERE m.ConversationID=:conversation_id "
            "ORDER BY m.MessageID ASC LIMIT 500"
        ),
        {"conversation_id": conversation_id},
    ).mappings().all()


def _serialize_messages(rows):
    return [
        {
            "id": row["MessageID"],
            "sender_type": row["SenderType"],
            "sender_name": row["SenderName"] or ("Nhân viên" if row["SenderType"] == "STAFF" else "Bạn"),
            "text": row["MessageText"],
            "created_at": row["CreatedAt"].isoformat() if row["CreatedAt"] else "",
        }
        for row in rows
    ]


def customer_chat():
    customer_id = _require_customer()
    token = _chat_token()
    with engine.begin() as connection:
        conversation_id = _ensure_conversation(connection, customer_id)
        messages = _messages(connection, conversation_id, mark_customer_read=customer_id)
    return render_template(
        "chat.html",
        csrf_token=token,
        messages=_serialize_messages(messages),
    )


def customer_messages():
    customer_id = _require_customer()
    if request.method == "POST":
        _check_chat_csrf()
        message = request.json.get("message", "") if request.is_json else request.form.get("message", "")
        message = (message or "").strip()
        if not message or len(message) > MAX_MESSAGE_LENGTH:
            return jsonify(error={"message": f"Tin nhắn phải từ 1 đến {MAX_MESSAGE_LENGTH} ký tự."}), 400
        with engine.begin() as connection:
            conversation_id = _ensure_conversation(connection, customer_id)
            insert_id(
                connection,
                "INSERT INTO Chat_Messages "
                "(ConversationID, SenderType, SenderCustomerID, MessageText) "
                "VALUES (:conversation_id, 'CUSTOMER', :customer_id, :message)",
                {"conversation_id": conversation_id, "customer_id": customer_id, "message": message},
                "MessageID",
            )
            connection.execute(
                text(
                    "UPDATE Chat_Conversations SET LastMessageAt=CURRENT_TIMESTAMP "
                    "WHERE ConversationID=:conversation_id"
                ),
                {"conversation_id": conversation_id},
            )
    with engine.begin() as connection:
        conversation_id = _ensure_conversation(connection, customer_id)
        messages = _messages(connection, conversation_id, mark_customer_read=customer_id)
    return jsonify(messages=_serialize_messages(messages))


def admin_chat():
    _require_staff()
    token = session.setdefault("dashboard_csrf_token", secrets.token_urlsafe(32))
    selected_id = request.args.get("customer_id", type=int)
    with engine.begin() as connection:
        customers = connection.execute(
            text(
                "SELECT c.CustomerID, c.FullName, c.Phone, "
                "COALESCE(cc.LastMessageAt, c.CreatedAt) AS LastMessageAt, "
                "(SELECT COUNT(*) FROM Chat_Messages cm "
                "WHERE cm.ConversationID=cc.ConversationID AND cm.SenderType='CUSTOMER' AND cm.IsRead=0) AS UnreadCount "
                "FROM Customers AS c LEFT JOIN Chat_Conversations AS cc ON cc.CustomerID=c.CustomerID "
                "WHERE c.IsDeleted=0 ORDER BY LastMessageAt DESC, c.FullName ASC"
            )
        ).mappings().all()
        messages = []
        if selected_id:
            conversation = connection.execute(
                text("SELECT ConversationID FROM Chat_Conversations WHERE CustomerID=:customer_id"),
                {"customer_id": selected_id},
            ).mappings().first()
            if conversation:
                messages = _messages(connection, conversation["ConversationID"], mark_staff_read=True)
    return render_template(
        "admin_chat.html",
        csrf_token=token,
        customers=customers,
        selected_customer_id=selected_id,
        messages=_serialize_messages(messages),
    )


def admin_messages(customer_id):
    _require_staff()
    with engine.begin() as connection:
        conversation = connection.execute(
            text("SELECT ConversationID FROM Chat_Conversations WHERE CustomerID=:customer_id"),
            {"customer_id": customer_id},
        ).mappings().first()
        if not conversation:
            return jsonify(messages=[])
        messages = _messages(connection, conversation["ConversationID"], mark_staff_read=True)
    return jsonify(messages=_serialize_messages(messages))


def admin_send_message(customer_id):
    _require_staff()
    _check_chat_csrf()
    message = request.json.get("message", "") if request.is_json else request.form.get("message", "")
    message = (message or "").strip()
    if not message or len(message) > MAX_MESSAGE_LENGTH:
        return jsonify(error={"message": f"Tin nhắn phải từ 1 đến {MAX_MESSAGE_LENGTH} ký tự."}), 400
    with engine.begin() as connection:
        customer = connection.execute(
            text("SELECT CustomerID FROM Customers WHERE CustomerID=:customer_id AND IsDeleted=0"),
            {"customer_id": customer_id},
        ).mappings().first()
        if not customer:
            abort(404)
        conversation_id = _ensure_conversation(connection, customer_id)
        insert_id(
            connection,
            "INSERT INTO Chat_Messages "
            "(ConversationID, SenderType, SenderUserID, MessageText) "
            "VALUES (:conversation_id, 'STAFF', :user_id, :message)",
            {"conversation_id": conversation_id, "user_id": session["user_id"], "message": message},
            "MessageID",
        )
        connection.execute(
            text(
                "UPDATE Chat_Conversations SET LastMessageAt=CURRENT_TIMESTAMP "
                "WHERE ConversationID=:conversation_id"
            ),
            {"conversation_id": conversation_id},
        )
    return admin_messages(customer_id)
