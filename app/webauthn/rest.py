from flask import Blueprint, current_app, jsonify, request

from app.dao.users_dao import get_user_by_id
from app.dao.webauthn_credential_dao import (
    dao_create_webauthn_credential,
    dao_delete_webauthn_credential,
    dao_get_webauthn_credential_by_user_and_id,
    dao_update_webauthn_credential_name,
)
from app.errors import InvalidRequest, register_errors
from app.schema_validation import validate
from app.user.utils import send_security_change_email
from app.webauthn.utils import send_security_key_change_email
from app.webauthn.webauthn_schema import (
    post_create_webauthn_credential_schema,
    post_update_webauthn_credential_schema,
)

webauthn_blueprint = Blueprint("webauthn", __name__, url_prefix="/user/<uuid:user_id>/webauthn")
register_errors(webauthn_blueprint)


@webauthn_blueprint.route("", methods=["GET"])
def get_webauthn_credentials(user_id):
    user = get_user_by_id(user_id)
    return jsonify(data=[cred.serialize() for cred in user.webauthn_credentials]), 200


@webauthn_blueprint.route("", methods=["POST"])
def create_webauthn_credential(user_id):
    data = request.get_json()
    user = get_user_by_id(user_id)
    validate(data, post_create_webauthn_credential_schema)
    webauthn_credential = dao_create_webauthn_credential(
        user_id=user_id,
        name=data["name"],
        credential_data=data["credential_data"],
        registration_response=data["registration_response"],
    )
    send_security_change_email(
        current_app.config["SECURITY_INFO_CHANGE_EMAIL_TEMPLATE_ID"],
        user.email_address,
        current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        user.name,
        "security key",
    )
    send_security_key_change_email(
        user.email_address,
        current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        user.name,
        "added to",
        "add this security key to",
    )

    return jsonify(data=webauthn_credential.serialize()), 201


@webauthn_blueprint.route("/<uuid:webauthn_credential_id>", methods=["POST"])
def update_webauthn_credential(user_id, webauthn_credential_id):
    data = request.get_json()
    validate(data, post_update_webauthn_credential_schema)

    webauthn_credential = dao_get_webauthn_credential_by_user_and_id(user_id, webauthn_credential_id)

    dao_update_webauthn_credential_name(webauthn_credential, data["name"])

    return jsonify(data=webauthn_credential.serialize()), 200


@webauthn_blueprint.route("/<uuid:webauthn_credential_id>", methods=["DELETE"])
def delete_webauthn_credential(user_id, webauthn_credential_id):
    webauthn_credential = dao_get_webauthn_credential_by_user_and_id(user_id, webauthn_credential_id)
    user = get_user_by_id(user_id)

    if len(user.webauthn_credentials) == 1:
        # TODO: Only raise an error if user has auth type webauthn_auth
        raise InvalidRequest("Cannot delete last remaining webauthn credential for user", status_code=400)

    dao_delete_webauthn_credential(webauthn_credential)
    send_security_key_change_email(
        user.email_address,
        current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        user.name,
        "deleted from",
        "delete this security key from",
    )

    return "", 204
