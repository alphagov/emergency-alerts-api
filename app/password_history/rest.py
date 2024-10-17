from flask import Blueprint

from app.dao.password_history_dao import (
    dao_create_password_for_user_id,
    dao_get_all_passwords_for_user,
)
from app.errors import register_errors
from app.hashing import check_hash

password_history_blueprint = Blueprint(
    "password_history",
    __name__,
    url_prefix="/password_history",
)

register_errors(password_history_blueprint)


@password_history_blueprint.route("")
def add_old_password_for_user(user_id, password):
    dao_create_password_for_user_id(user_id, password)


def is_password_for_user_already_in_table(user_id, password):
    data = dao_get_all_passwords_for_user(user_id)
    passwords = [item._password for item in data]
    return any(check_hash(password, hashed_password) for hashed_password in passwords)
    # returns whether or not password already exists
