import logging
import os
import secrets

import bcrypt
from flask import Flask, flash, redirect, render_template, request, session, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from database import engine

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
logger = logging.getLogger(__name__)


@app.route("/")
def index():
    products = []
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("SELECT ProductName, SellingPrice, MainImage FROM Products")
            )
            products = result.fetchall()
    except Exception:
        logger.exception("Không thể tải danh sách sản phẩm")

    return render_template("index.html", products=products)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("index"))

    identity = ""
    if request.method == "POST":
        identity = request.form.get("identity", "").strip()
        password = request.form.get("password", "")

        if not identity or not password:
            flash("Vui lòng nhập email/số điện thoại và mật khẩu.", "error")
            return render_template("login.html", identity=identity)

        try:
            with engine.connect() as connection:
                customer = connection.execute(
                    text(
                        "SELECT CustomerID, FullName, PasswordHash "
                        "FROM Customers "
                        "WHERE (Phone = :identity OR Email = :identity) "
                        "AND IsDeleted = 0 AND PasswordHash IS NOT NULL"
                    ),
                    {"identity": identity},
                ).mappings().first()

                if customer and bcrypt.checkpw(
                    password.encode("utf-8"),
                    customer["PasswordHash"].encode("utf-8"),
                ):
                    session.clear()
                    session["user_id"] = customer["CustomerID"]
                    session["user_type"] = "customer"
                    session["full_name"] = customer["FullName"]
                    flash(f"Đăng nhập thành công. Xin chào {customer['FullName']}!", "success")
                    return redirect(url_for("index"))

                user = connection.execute(
                    text(
                        "SELECT UserID, Username, PasswordHash, FullName, RoleID "
                        "FROM Users "
                        "WHERE (Username = :identity OR Email = :identity) "
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

        flash("Email/số điện thoại hoặc mật khẩu không đúng.", "error")

    return render_template("login.html", identity=identity)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("index"))

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip() or None
        phone = request.form.get("phone", "").strip() or None
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not phone or not password:
            flash("Vui lòng điền họ tên, số điện thoại và mật khẩu.", "error")
        elif len(full_name) > 100:
            flash("Họ tên tối đa 100 ký tự.", "error")
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
                            "WHERE Phone = :phone "
                            "OR (:email IS NOT NULL AND Email = :email)"
                        ),
                        {"phone": phone, "email": email},
                    ).first()
                    if existing_customer:
                        flash("Số điện thoại hoặc email đã được sử dụng.", "error")
                        return render_template("register.html")

                    connection.execute(
                        text(
                            "INSERT INTO Customers "
                            "(FullName, Phone, Email, PasswordHash) "
                            "VALUES (:full_name, :phone, :email, :password_hash)"
                        ),
                        {
                            "password_hash": password_hash,
                            "full_name": full_name,
                            "email": email,
                            "phone": phone,
                        },
                    )
            except IntegrityError:
                flash("Số điện thoại hoặc email đã được sử dụng.", "error")
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