import os

from flask import Blueprint

from app.dao.users_dao import get_code_for_user
from app.errors import InvalidRequest

verify_code_blueprint = Blueprint("verify", __name__)


@verify_code_blueprint.route("/<uuid:user_id>", methods=["GET"])
def get_latest_verify_code_for_user(user_id):
    if os.environ.get("ENVIRONMENT") not in ["local", "development", "preview"]:
        raise InvalidRequest("Endpoint not found", status_code=404)

    return get_code_for_user(user_id)
