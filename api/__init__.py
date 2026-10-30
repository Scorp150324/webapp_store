import logging
from http import HTTPStatus

from flask import Blueprint, jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)
api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.errorhandler(HTTPException)
def handle_api_http_error(error):
    status_code = error.code or 500
    try:
        error_code = HTTPStatus(status_code).phrase.lower().replace(" ", "_")
    except ValueError:
        error_code = "http_error"
    return jsonify(error={"code": error_code, "message": error.description}), status_code


@api_bp.errorhandler(Exception)
def handle_api_unexpected_error(error):
    logger.exception("Unhandled API error", exc_info=error)
    return (
        jsonify(
            error={
                "code": "internal_server_error",
                "message": "Đã xảy ra lỗi ngoài dự kiến. Vui lòng thử lại sau.",
            }
        ),
        500,
    )


from api import admin, auth, products  # noqa: E402,F401
