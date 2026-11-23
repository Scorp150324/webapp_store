import logging
import secrets
import hmac

from flask import abort, jsonify, render_template, request, session
from sqlalchemy.exc import SQLAlchemyError

from database import engine, ensure_customer_presence_schema, insert_id, text

logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 2000


def _bot_reply(message):
    """Return a short fallback reply while no staff member owns the chat."""
    normalized = message.casefold()
    if any(word in normalized for word in ("xin chào", "chào", "hello", "hi")):
        return "Xin chào! Trợ lý tự động đã nhận được tin nhắn của bạn."
    if any(word in normalized for word in ("giá", "sản phẩm", "sp", "mã hàng")):
        return "Bạn có thể xem giá và thông tin sản phẩm ngay trên cửa hàng. Tin nhắn của bạn đã được ghi nhận để admin hỗ trợ thêm khi online."
    if any(word in normalized for word in ("đơn hàng", "đặt hàng", "mua hàng", "giao hàng")):
        return "Yêu cầu về đơn hàng đã được ghi nhận. Admin sẽ kiểm tra và phản hồi trong cuộc trò chuyện này khi online."
    if any(word in normalized for word in ("bảo hành", "bảo hành", "sửa chữa")):
        return "Yêu cầu bảo hành đã được ghi nhận. Vui lòng giữ lại mã đơn hàng để admin kiểm tra nhanh hơn."
    return "Mình đã ghi nhận tin nhắn của bạn. Hiện chưa có admin trực tuyến; admin sẽ tiếp tục trao đổi trong cuộc trò chuyện này khi online."


def _require_customer():
    if session.get("user_type") != "customer" or not session.get("user_id"):
        abort(403)
    return int(session["user_id"])


def _require_staff():
    if session.get("user_type") != "staff" or session.get("role_id") not in {1, 5}:
        abort(403)
    return int(session["user_id"])


def _check_chat_csrf():
    expected = (
        session.get("dashboard_csrf_token", "")
        if session.get("user_type") == "staff"
        else session.get("chat_csrf_token", "")
    )
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
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
            "sender_name": row["SenderName"] or (
                "Trợ lý tự động"
                if row["SenderType"] == "BOT"
                else "Nhân viên"
                if row["SenderType"] == "STAFF"
                else "Bạn"
            ),
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
            staff_message = connection.execute(
                text(
                    "SELECT 1 FROM Chat_Messages "
                    "WHERE ConversationID=:conversation_id AND SenderType='STAFF' LIMIT 1"
                ),
                {"conversation_id": conversation_id},
            ).first()
            if not staff_message:
                insert_id(
                    connection,
                    "INSERT INTO Chat_Messages "
                    "(ConversationID, SenderType, MessageText) "
                    "VALUES (:conversation_id, 'BOT', :message)",
                    {"conversation_id": conversation_id, "message": _bot_reply(message)},
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
    customers = []
    messages = []
    data_unavailable = False
    try:
        ensure_customer_presence_schema()
        with engine.begin() as connection:
            customers = connection.execute(
                text(
                    "SELECT c.CustomerID, c.FullName, c.Phone, "
                    "CASE WHEN c.IsOnline=1 AND c.LastSeenAt > CURRENT_TIMESTAMP - INTERVAL '3 minutes' "
                    "THEN 1 ELSE 0 END AS IsOnline, c.LastSeenAt, "
                    "COALESCE(cc.LastMessageAt, c.CreatedAt) AS LastMessageAt, "
                    "(SELECT COUNT(*) FROM Chat_Messages cm "
                    "WHERE cm.ConversationID=cc.ConversationID AND cm.SenderType='CUSTOMER' AND cm.IsRead=0) AS UnreadCount "
                    "FROM Customers AS c LEFT JOIN Chat_Conversations AS cc ON cc.CustomerID=c.CustomerID "
                    "WHERE c.IsDeleted=0 ORDER BY LastMessageAt DESC, c.FullName ASC"
                )
            ).mappings().all()
            if selected_id:
                conversation = connection.execute(
                    text("SELECT ConversationID FROM Chat_Conversations WHERE CustomerID=:customer_id"),
                    {"customer_id": selected_id},
                ).mappings().first()
                if conversation:
                    messages = _messages(connection, conversation["ConversationID"], mark_staff_read=True)
    except SQLAlchemyError:
        logger.exception("Không thể tải dữ liệu chat admin; hiển thị giao diện rỗng")
        data_unavailable = True
        selected_id = None
    return render_template(
        "admin_chat.html",
        csrf_token=token,
        customers=customers,
        selected_customer_id=selected_id,
        messages=_serialize_messages(messages),
        data_unavailable=data_unavailable,
    )


def admin_messages(customer_id):
    _require_staff()
    ensure_customer_presence_schema()
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE Customers SET IsOnline=0 WHERE CustomerID=:customer_id "
                "AND IsOnline=1 AND LastSeenAt <= CURRENT_TIMESTAMP - INTERVAL '3 minutes'"
            ),
            {"customer_id": customer_id},
        )
        customer = connection.execute(
            text(
                "SELECT IsOnline FROM Customers "
                "WHERE CustomerID=:customer_id AND IsDeleted=0"
            ),
            {"customer_id": customer_id},
        ).mappings().first()
        if not customer:
            abort(404)
        conversation = connection.execute(
            text("SELECT ConversationID FROM Chat_Conversations WHERE CustomerID=:customer_id"),
            {"customer_id": customer_id},
        ).mappings().first()
        if not conversation:
            return jsonify(messages=[], customer_online=bool(customer["IsOnline"]))
        messages = _messages(connection, conversation["ConversationID"], mark_staff_read=True)
    return jsonify(
        messages=_serialize_messages(messages),
        customer_online=bool(customer["IsOnline"]),
    )


def customer_presence():
    customer_id = _require_customer()
    ensure_customer_presence_schema()
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE Customers SET IsOnline=1, LastSeenAt=CURRENT_TIMESTAMP "
                "WHERE CustomerID=:customer_id AND IsDeleted=0"
            ),
            {"customer_id": customer_id},
        )
    return jsonify(ok=True)


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
