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

    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Vui lòng nhập tên đăng nhập/email và mật khẩu.", "error")
            return render_template("login.html", username=username)

        try:
            with engine.connect() as connection:
                user = connection.execute(
                    text(
                        "SELECT UserID, Username, PasswordHash, FullName, RoleID "
                        "FROM Users "
                        "WHERE (Username = :identity OR Email = :identity) "
                        "AND IsDeleted = 0"
                    ),
                    {"identity": username},
                ).mappings().first()

            if user and bcrypt.checkpw(
                password.encode("utf-8"), user["PasswordHash"].encode("utf-8")
            ):
                session.clear()
                session["user_id"] = user["UserID"]
                session["username"] = user["Username"]
                session["full_name"] = user["FullName"]
                session["role_id"] = user["RoleID"]
                flash(f"Đăng nhập thành công. Xin chào {user['FullName']}!", "success")
                return redirect(url_for("index"))
        except ValueError:
            logger.exception("Hash mật khẩu trong cơ sở dữ liệu không hợp lệ")
            flash("Không thể xác thực tài khoản. Vui lòng liên hệ quản trị viên.", "error")
            return render_template("login.html", username=username)
        except Exception:
            logger.exception("Không thể đăng nhập do lỗi truy cập cơ sở dữ liệu")
            flash("Không thể kết nối cơ sở dữ liệu. Vui lòng thử lại sau.", "error")
            return render_template("login.html", username=username)

        flash("Tên đăng nhập/email hoặc mật khẩu không đúng.", "error")

    return render_template("login.html", username=username)


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

        if not full_name or not username or not password:
            flash("Vui lòng điền họ tên, tên đăng nhập và mật khẩu.", "error")
        elif len(full_name) > 100 or len(username) > 50:
            flash("Họ tên tối đa 100 ký tự, tên đăng nhập tối đa 50 ký tự.", "error")
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
                    connection.execute(
                        text(
                            "INSERT INTO Users "
                            "(RoleID, Username, PasswordHash, FullName, Email, Phone) "
                            "VALUES (NULL, :username, :password_hash, :full_name, :email, :phone)"
                        ),
                        {
                            "username": username,
                            "password_hash": password_hash,
                            "full_name": full_name,
                            "email": email,
                            "phone": phone,
                        },
                    )
            except IntegrityError:
                flash("Tên đăng nhập hoặc email đã được sử dụng.", "error")
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