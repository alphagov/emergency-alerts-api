from flask import Blueprint

from app.dao.users_dao import get_code_for_user

verify_code_blueprint = Blueprint("verify", __name__)


@verify_code_blueprint.route("/<uuid:user_id>", methods=["GET"])
def get_latest_verify_code_for_user(user_id):
    return get_code_for_user(user_id)
