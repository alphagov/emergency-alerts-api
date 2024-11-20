from flask import Blueprint

from app.dao.common_passwords_dao import dao_get_common_password_by_password
from app.errors import register_errors

common_passwords_blueprint = Blueprint(
    "common_passwords",
    __name__,
    url_prefix="/common_passwords",
)

register_errors(common_passwords_blueprint)


@common_passwords_blueprint.route("")
def is_password_common(password):
    data = dao_get_common_password_by_password(password)
    return bool(data)
    # returns whether or not password is common
