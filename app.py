import logging
import os
import secrets
from http import HTTPStatus
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

load_dotenv()

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent


def create_app():
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key and os.environ.get("FLASK_ENV", "").strip().lower() == "production":
        raise RuntimeError("SECRET_KEY must be configured in production")

    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.secret_key = secret_key or secrets.token_hex(32)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = (
        os.environ.get("FLASK_ENV", "").strip().lower() == "production"
    )
    app.config["IMAGE_FOLDER"] = str(PROJECT_ROOT / "image")

    from api import api_bp
    from controllers.admin import dashboard_bp
    from controllers.customer import customer_bp
    from controllers.site import site_bp

    app.register_blueprint(site_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(api_bp)

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        if error.code is not None and error.code >= 500:
            logger.error("HTTP error %s at %s", error.code, request.path)
        if request.path.startswith("/api/"):
            status_code = error.code or 500
            try:
                error_code = HTTPStatus(status_code).phrase.lower().replace(" ", "_")
            except ValueError:
                error_code = "http_error"
            return (
                jsonify(
                    error={
                        "code": error_code,
                        "message": error.description,
                    }
                ),
                status_code,
            )
        return (
            render_template(
                "errors/error.html",
                status_code=error.code or 500,
                message=error.description,
            ),
            error.code or 500,
        )

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error):
        logger.exception("Unhandled database error at %s", request.path, exc_info=error)
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    error={
                        "code": "service_unavailable",
                        "message": "Không thể kết nối hoặc truy vấn cơ sở dữ liệu. Vui lòng thử lại sau.",
                    }
                ),
                503,
            )
        return (
            render_template(
                "errors/error.html",
                status_code=503,
                message="Không thể kết nối hoặc truy vấn cơ sở dữ liệu. Vui lòng thử lại sau.",
            ),
            503,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        logger.exception("Unhandled application error at %s", request.path, exc_info=error)
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    error={
                        "code": "internal_server_error",
                        "message": "Đã xảy ra lỗi ngoài dự kiến. Vui lòng thử lại sau.",
                    }
                ),
                500,
            )
        return (
            render_template(
                "errors/error.html",
                status_code=500,
                message="Đã xảy ra lỗi ngoài dự kiến. Vui lòng thử lại sau.",
            ),
            500,
        )

    return app


app = create_app()
