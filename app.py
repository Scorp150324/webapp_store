import hashlib
import hmac
import json
import logging
import os
import secrets
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

from dotenv import load_dotenv
import bcrypt
from flask import Flask, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from admin import dashboard_bp
from database import engine

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
logger = logging.getLogger(__name__)
app.register_blueprint(dashboard_bp)

PASSWORD_RESET_OTP_TTL_MINUTES = 10
PASSWORD_RESET_MAX_ATTEMPTS = 5
PASSWORD_RESET_MAX_SENDS_PER_HOUR = 3


def _password_reset_token_hash(customer_id, otp):
    message = f"{customer_id}:{otp}".encode("utf-8")
    return hmac.new(
        app.secret_key.encode("utf-8"), message, hashlib.sha256
    ).hexdigest()


def _send_password_reset_email(email, otp):
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    sender = os.environ.get("SMTP_FROM_EMAIL") or smtp_username
    if not smtp_host or not sender:
        raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL must be configured")

    message = EmailMessage()
    message["Subject"] = "Mã OTP đặt lại mật khẩu"
    sender_name = os.environ.get("SMTP_FROM_NAME", "").strip()
    message["From"] = formataddr((sender_name, sender)) if sender_name else sender
    message["To"] = email
    message.set_content(
        f"Mã OTP đặt lại mật khẩu của bạn là {otp}. "
        f"Mã có hiệu lực trong {PASSWORD_RESET_OTP_TTL_MINUTES} phút."
    )

    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    timeout = 10
    if os.environ.get("SMTP_USE_SSL", "").lower() in {"1", "true", "yes"}:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=timeout) as smtp:
            if smtp_username:
                smtp.login(smtp_username, smtp_password or "")
            smtp.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as smtp:
        smtp.ehlo()
        if os.environ.get("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}:
            smtp.starttls()
            smtp.ehlo()
        if smtp_username:
            smtp.login(smtp_username, smtp_password or "")
        smtp.send_message(message)


def _send_password_reset_sms(phone, otp):
    api_key = os.environ.get("ESMS_API_KEY")
    secret_key = os.environ.get("ESMS_SECRET_KEY")
    brand_name = os.environ.get("ESMS_BRAND_NAME")
    if not api_key or not secret_key or not brand_name:
        raise RuntimeError(
            "ESMS_API_KEY, ESMS_SECRET_KEY and ESMS_BRAND_NAME must be configured"
        )

    payload = {
        "ApiKey": api_key,
        "SecretKey": secret_key,
        "Phone": phone,
        "Content": (
            f"Ma OTP dat lai mat khau cua ban la {otp}. "
            f"Ma co hieu luc trong {PASSWORD_RESET_OTP_TTL_MINUTES} phut."
        ),
        "Brandname": brand_name,
        "SmsType": os.environ.get("ESMS_SMS_TYPE", "2"),
    }
    endpoint = os.environ.get(
        "ESMS_API_URL",
        "https://rest.esms.vn/MainService.svc/json/SendMultipleMessage_V4_post_json/",
    )
    body = json.dumps(payload).encode("utf-8")
    api_request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(api_request, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError("eSMS returned an invalid response")
    if str(result.get("CodeResult", "")) != "1000":
        raise RuntimeError(
            f"eSMS rejected the OTP message (CodeResult={result.get('CodeResult')})"
        )


PRODUCT_CATEGORIES = {
    "pc": {
        "label": "PC",
        "root_names": {"máy tính để bàn (pc)"},
    },
    "laptop": {
        "label": "Laptop",
        "root_names": {"laptop"},
    },
    "phone": {
        "label": "Điện thoại",
        "root_names": {"điện thoại thông minh"},
    },
    "printer": {
        "label": "Máy in",
        "root_names": {"máy in & thiết bị văn phòng"},
    },
    "camera": {
        "label": "Camera",
        "root_names": {"camera & thiết bị an ninh"},
    },
    "accessories": {
        "label": "Phụ kiện khác",
        "root_names": {"linh kiện máy tính", "phụ kiện & thiết bị ngoại vi"},
    },
}


@app.route("/")
def index():
    products = []
    search = request.args.get("q", "").strip()[:100]
    selected_category = request.args.get("category", "")
    if selected_category not in PRODUCT_CATEGORIES:
        selected_category = ""

    try:
        with engine.connect() as connection:
            category_rows = connection.execute(
                text("SELECT CategoryID, CategoryName, ParentID FROM Categories")
            ).mappings().all()
            child_ids_by_parent = {}
            for row in category_rows:
                if row["ParentID"] is not None:
                    child_ids_by_parent.setdefault(row["ParentID"], set()).add(
                        row["CategoryID"]
                    )

            category_ids = set()
            if selected_category:
                root_names = PRODUCT_CATEGORIES[selected_category]["root_names"]
                root_ids = {
                    row["CategoryID"]
                    for row in category_rows
                    if row["ParentID"] is None
                    and row["CategoryName"].strip().casefold() in root_names
                }
                category_ids.update(root_ids)
                pending_ids = list(root_ids)
                while pending_ids:
                    parent_id = pending_ids.pop()
                    for child_id in child_ids_by_parent.get(parent_id, set()):
                        if child_id not in category_ids:
                            category_ids.add(child_id)
                            pending_ids.append(child_id)

            query = (
                "SELECT p.ProductName, p.SellingPrice, p.MainImage, "
                "p.SKU, p.Barcode, c.CategoryName "
                "FROM Products AS p "
                "LEFT JOIN Categories AS c ON c.CategoryID = p.CategoryID "
                "WHERE p.IsDeleted = 0"
            )
            parameters = {}
            if search:
                query += (
                    " AND (p.ProductName LIKE :search "
                    "OR p.SKU LIKE :search "
                    "OR p.Barcode LIKE :search "
                    "OR p.Specifications LIKE :search)"
                )
                parameters["search"] = f"%{search}%"
            if selected_category:
                if category_ids:
                    category_parameters = []
                    for index, category_id in enumerate(sorted(category_ids)):
                        parameter_name = f"category_id_{index}"
                        category_parameters.append(f":{parameter_name}")
                        parameters[parameter_name] = category_id
                    query += f" AND p.CategoryID IN ({', '.join(category_parameters)})"
                else:
                    query += " AND 1 = 0"

            result = connection.execute(
                text(query), parameters
            )
            products = result.fetchall()
    except Exception:
        logger.exception("Không thể tải danh sách sản phẩm")

    return render_template(
        "index.html",
        products=products,
        search=search,
        selected_category=selected_category,
        product_categories=PRODUCT_CATEGORIES,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    identity = ""
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")

        if not identity or not password:
            flash("Vui lòng nhập tên tài khoản, email hoặc số điện thoại và mật khẩu.", "error")
            return render_template("login.html", identity=identity)

        try:
            with engine.connect() as connection:
                customer = connection.execute(
                    text(
                        "SELECT CustomerID, FullName, PasswordHash "
                        "FROM Customers "
                        "WHERE (Username = :identity OR Phone = :identity "
                        "OR Email = :identity) "
                        "AND IsDeleted = 0 AND PasswordHash IS NOT NULL"
                    ),
                    {"identity": identity},
                ).mappings().first()

                if customer:
                    try:
                        password_matches = bcrypt.checkpw(
                            password.encode("utf-8"),
                            customer["PasswordHash"].encode("utf-8"),
                        )
                    except ValueError:
                        logger.exception(
                            "Hash mật khẩu khách hàng không hợp lệ (CustomerID=%s)",
                            customer["CustomerID"],
                        )
                        password_matches = False

                    if password_matches:
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
                            logger.exception(
                                "Không thể ghi nhật ký đăng nhập khách hàng"
                            )

                        session.clear()
                        session["user_id"] = customer["CustomerID"]
                        session["user_type"] = "customer"
                        session["full_name"] = customer["FullName"]
                        flash(
                            f"Đăng nhập thành công. Xin chào {customer['FullName']}!",
                            "success",
                        )
                        return redirect(url_for("index"))

                user = connection.execute(
                    text(
                        "SELECT UserID, Username, PasswordHash, FullName, RoleID "
                        "FROM Users "
                        "WHERE (Username = :identity OR Email = :identity "
                        "OR Phone = :identity) "
                        "AND IsDeleted = 0"
                    ),
                    {"identity": identity},
                ).mappings().first()

            if user and bcrypt.checkpw(
                password.encode("utf-8"), user["PasswordHash"].encode("utf-8")
            ):
                session.clear()
                session["user_id"] = user["UserID"]
                session["user_type"] = "staff"
                session["username"] = user["Username"]
                session["full_name"] = user["FullName"]
                session["role_id"] = user["RoleID"]
                flash(f"Đăng nhập thành công. Xin chào {user['FullName']}!", "success")
                return redirect(url_for("index"))
        except ValueError:
            logger.exception("Hash mật khẩu trong cơ sở dữ liệu không hợp lệ")
            flash("Không thể xác thực tài khoản. Vui lòng liên hệ quản trị viên.", "error")
            return render_template("login.html", identity=identity)
        except Exception:
            logger.exception("Không thể đăng nhập do lỗi truy cập cơ sở dữ liệu")
            flash("Không thể kết nối cơ sở dữ liệu. Vui lòng thử lại sau.", "error")
            return render_template("login.html", identity=identity)

        flash("Tên tài khoản, email, số điện thoại hoặc mật khẩu không đúng.", "error")

    return render_template("login.html", identity=identity)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "GET" and request.args.get("new") == "1":
        session.pop("password_reset_requested", None)
        session.pop("password_reset_id", None)
        session.pop("password_reset_customer_id", None)

    stage = (
        "verify"
        if session.get("password_reset_requested")
        and request.args.get("new") != "1"
        else "request"
    )

    if request.method == "POST":
        submitted_stage = request.form.get("stage", "request")

        if submitted_stage == "request":
            identity = request.form.get("identity", "").strip()
            if not identity or len(identity) > 100:
                flash("Vui lòng nhập email hoặc số điện thoại hợp lệ.", "error")
                return render_template("forgot_password.html", stage="request")

            email_identity = "@" in identity
            lookup = (
                "SELECT CustomerID, Email, Phone FROM Customers "
                "WHERE Email = :identity AND IsDeleted = 0 FOR UPDATE"
                if email_identity
                else "SELECT CustomerID, Email, Phone FROM Customers "
                "WHERE Phone = :identity AND IsDeleted = 0 FOR UPDATE"
            )
            session.pop("password_reset_requested", None)
            session.pop("password_reset_id", None)
            session.pop("password_reset_customer_id", None)

            try:
                reset_request = None
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "DELETE FROM Password_Reset_Tokens "
                            "WHERE ExpiresAt < DATE_SUB(NOW(), INTERVAL 1 DAY)"
                        )
                    )
                    customer = connection.execute(
                        text(lookup), {"identity": identity}
                    ).mappings().first()

                    if customer:
                        send_count = connection.execute(
                            text(
                                "SELECT COUNT(*) FROM Password_Reset_Tokens "
                                "WHERE CustomerID = :customer_id "
                                "AND CreatedAt >= DATE_SUB(NOW(), INTERVAL 1 HOUR)"
                            ),
                            {"customer_id": customer["CustomerID"]},
                        ).scalar_one()
                        if send_count < PASSWORD_RESET_MAX_SENDS_PER_HOUR:
                            otp = f"{secrets.randbelow(1_000_000):06d}"
                            token_hash = _password_reset_token_hash(
                                customer["CustomerID"], otp
                            )
                            connection.execute(
                                text(
                                    "UPDATE Password_Reset_Tokens SET UsedAt = NOW() "
                                    "WHERE CustomerID = :customer_id AND UsedAt IS NULL"
                                ),
                                {"customer_id": customer["CustomerID"]},
                            )
                            result = connection.execute(
                                text(
                                    "INSERT INTO Password_Reset_Tokens "
                                    "(CustomerID, TokenHash, ExpiresAt, FailedAttempts) "
                                    "VALUES (:customer_id, :token_hash, "
                                    "DATE_ADD(NOW(), INTERVAL "
                                    f"{PASSWORD_RESET_OTP_TTL_MINUTES} MINUTE), 0)"
                                ),
                                {
                                    "customer_id": customer["CustomerID"],
                                    "token_hash": token_hash,
                                },
                            )
                            reset_id = result.lastrowid
                            destination = (
                                customer["Email"] if email_identity else customer["Phone"]
                            )
                            reset_request = {
                                "reset_id": reset_id,
                                "customer_id": customer["CustomerID"],
                                "destination": destination,
                                "email": email_identity,
                                "otp": otp,
                            }

                if reset_request:
                    try:
                        if reset_request["email"]:
                            _send_password_reset_email(
                                reset_request["destination"], reset_request["otp"]
                            )
                        else:
                            _send_password_reset_sms(
                                reset_request["destination"], reset_request["otp"]
                            )
                    except (
                        OSError,
                        RuntimeError,
                        ValueError,
                        smtplib.SMTPException,
                        urllib.error.URLError,
                    ):
                        with engine.begin() as connection:
                            connection.execute(
                                text(
                                    "UPDATE Password_Reset_Tokens SET UsedAt = NOW() "
                                    "WHERE PasswordResetID = :reset_id "
                                    "AND UsedAt IS NULL"
                                ),
                                {"reset_id": reset_request["reset_id"]},
                            )
                        raise

                    session["password_reset_id"] = reset_request["reset_id"]
                    session["password_reset_customer_id"] = reset_request[
                        "customer_id"
                    ]

                session["password_reset_requested"] = True
                flash(
                    "Nếu thông tin tồn tại và đủ điều kiện, mã OTP sẽ được gửi "
                    "đến email hoặc số điện thoại của bạn.",
                    "success",
                )
                return redirect(url_for("forgot_password"))
            except (
                SQLAlchemyError,
                OSError,
                RuntimeError,
                ValueError,
                smtplib.SMTPException,
                urllib.error.URLError,
            ):
                logger.exception("Không thể gửi OTP đặt lại mật khẩu")
                flash(
                    "Không thể gửi mã OTP lúc này. Vui lòng thử lại sau.",
                    "error",
                )
                return render_template("forgot_password.html", stage="request")

        if submitted_stage == "verify":
            otp = request.form.get("otp", "").strip()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            stage = "verify"

            if len(password) < 8 or len(password.encode("utf-8")) > 72:
                flash("Mật khẩu cần ít nhất 8 ký tự và tối đa 72 byte.", "error")
            elif password != confirm_password:
                flash("Mật khẩu xác nhận không khớp.", "error")
            elif len(otp) != 6 or not otp.isdigit():
                flash("Vui lòng nhập mã OTP gồm 6 chữ số.", "error")
            else:
                reset_id = session.get("password_reset_id")
                customer_id = session.get("password_reset_customer_id")
                password_changed = False
                try:
                    with engine.begin() as connection:
                        reset_record = None
                        if reset_id and customer_id:
                            reset_record = connection.execute(
                                text(
                                    "SELECT CustomerID, TokenHash, FailedAttempts "
                                    "FROM Password_Reset_Tokens "
                                    "WHERE PasswordResetID = :reset_id "
                                    "AND CustomerID = :customer_id "
                                    "AND UsedAt IS NULL AND ExpiresAt > NOW() "
                                    "FOR UPDATE"
                                ),
                                {
                                    "reset_id": reset_id,
                                    "customer_id": customer_id,
                                },
                            ).mappings().first()

                        if reset_record and hmac.compare_digest(
                            reset_record["TokenHash"],
                            _password_reset_token_hash(customer_id, otp),
                        ):
                            password_hash = bcrypt.hashpw(
                                password.encode("utf-8"), bcrypt.gensalt()
                            ).decode("utf-8")
                            update_result = connection.execute(
                                text(
                                    "UPDATE Customers SET PasswordHash = :password_hash "
                                    "WHERE CustomerID = :customer_id AND IsDeleted = 0"
                                ),
                                {
                                    "password_hash": password_hash,
                                    "customer_id": customer_id,
                                },
                            )
                            if update_result.rowcount != 1:
                                raise RuntimeError(
                                    "Customer account was not updated during password reset"
                                )
                            connection.execute(
                                text(
                                    "UPDATE Password_Reset_Tokens SET UsedAt = NOW() "
                                    "WHERE CustomerID = :customer_id AND UsedAt IS NULL"
                                ),
                                {"customer_id": customer_id},
                            )
                            password_changed = True

                        elif reset_record:
                            attempts = reset_record["FailedAttempts"] + 1
                            connection.execute(
                                text(
                                    "UPDATE Password_Reset_Tokens "
                                    "SET FailedAttempts = :attempts, "
                                    "UsedAt = CASE WHEN :attempts >= :max_attempts "
                                    "THEN NOW() ELSE UsedAt END "
                                    "WHERE PasswordResetID = :reset_id"
                                ),
                                {
                                    "attempts": attempts,
                                    "max_attempts": PASSWORD_RESET_MAX_ATTEMPTS,
                                    "reset_id": reset_id,
                                },
                            )
                    if password_changed:
                        session.pop("password_reset_requested", None)
                        session.pop("password_reset_id", None)
                        session.pop("password_reset_customer_id", None)
                        flash(
                            "Đổi mật khẩu thành công. Vui lòng đăng nhập lại.",
                            "success",
                        )
                        return redirect(url_for("login"))
                    flash("Mã OTP không hợp lệ hoặc đã hết hạn.", "error")
                except (
                    SQLAlchemyError,
                    OSError,
                    RuntimeError,
                    ValueError,
                    smtplib.SMTPException,
                    urllib.error.URLError,
                ):
                    logger.exception("Không thể đổi mật khẩu khách hàng")
                    flash(
                        "Không thể đổi mật khẩu lúc này. Vui lòng thử lại sau.",
                        "error",
                    )

    return render_template("forgot_password.html", stage=stage)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip() or None
        phone = request.form.get("phone", "").strip() or None
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not username or not phone or not password:
            flash("Vui lòng điền tên tài khoản, họ tên, số điện thoại và mật khẩu.", "error")
        elif len(full_name) > 100:
            flash("Họ tên tối đa 100 ký tự.", "error")
        elif len(username) > 50:
            flash("Tên tài khoản không được dài quá 50 ký tự.", "error")
        elif email and len(email) > 100:
            flash("Email không được dài quá 100 ký tự.", "error")
        elif phone and len(phone) > 20:
            flash("Số điện thoại không được dài quá 20 ký tự.", "error")
        elif len(password) < 8 or len(password.encode("utf-8")) > 72:
            flash("Mật khẩu cần ít nhất 8 ký tự và tối đa 72 byte.", "error")
        elif password != confirm_password:
            flash("Mật khẩu xác nhận không khớp.", "error")
        else:
            password_hash = bcrypt.hashpw(
                password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            try:
                with engine.begin() as connection:
                    existing_customer = connection.execute(
                        text(
                            "SELECT CustomerID FROM Customers "
                            "WHERE Username = :username OR Phone = :phone "
                            "OR (:email IS NOT NULL AND Email = :email)"
                        ),
                        {"username": username, "phone": phone, "email": email},
                    ).first()
                    if existing_customer:
                        flash(
                            "Tên tài khoản, số điện thoại hoặc email đã được sử dụng.",
                            "error",
                        )
                        return render_template("register.html")

                    connection.execute(
                        text(
                            "INSERT INTO Customers "
                            "(Username, FullName, Phone, Email, PasswordHash) "
                            "VALUES (:username, :full_name, :phone, :email, :password_hash)"
                        ),
                        {
                            "password_hash": password_hash,
                            "username": username,
                            "full_name": full_name,
                            "email": email,
                            "phone": phone,
                        },
                    )
            except IntegrityError:
                flash(
                    "Tên tài khoản, số điện thoại hoặc email đã được sử dụng.",
                    "error",
                )
            except Exception:
                logger.exception("Không thể tạo tài khoản do lỗi truy cập cơ sở dữ liệu")
                flash("Không thể kết nối cơ sở dữ liệu. Vui lòng thử lại sau.", "error")
            else:
                flash("Đăng ký thành công. Vui lòng đăng nhập.", "success")
                return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Bạn đã đăng xuất.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)