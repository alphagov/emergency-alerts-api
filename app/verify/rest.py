from flask import Blueprint

from app.dao.users_dao import get_code_for_user
from app.errors import InvalidRequest
from app.utils import is_public_environment

verify_code_blueprint = Blueprint("verify", __name__)


@verify_code_blueprint.route("/<uuid:user_id>", methods=["GET"])
def get_latest_verify_code_for_user(user_id):
    if is_public_environment():
        raise InvalidRequest("Endpoint not found", status_code=404)

    return get_code_for_user(user_id)
