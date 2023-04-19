import json
import uuid
from datetime import datetime
from urllib.parse import urlencode

from flask import Blueprint, abort, current_app, jsonify, request
from notifications_python_client.errors import HTTPError
from sqlalchemy.exc import IntegrityError

from app.clients.notify_client import notify_send

from app.dao.permissions_dao import permission_dao
from app.dao.service_user_dao import (
    dao_get_service_user,
    dao_update_service_user,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.template_folder_dao import (
    dao_get_template_folder_by_id_and_service_id,
)

from app.dao.users_dao import (
    count_user_verify_codes,
    create_secret_code,
    create_user_code,
    dao_archive_user,
    get_user_and_accounts,
    get_user_by_email,
    get_user_by_id,
    get_user_code,
    get_users_by_partial_email,
    increment_failed_login_count,
    reset_failed_login_count,
    save_model_user,
    save_user_attribute,
    update_user_password,
    use_user_code,
)
from app.dao.webauthn_credential_dao import (
    dao_get_webauthn_credential_by_user_and_id,
    dao_update_webauthn_credential_logged_in_at,
)
from app.errors import InvalidRequest, register_errors
from app.models import EMAIL_TYPE, SMS_TYPE, Permission

from app.schema_validation import validate
from app.schemas import (
    create_user_schema,
    email_data_request_schema,
    partial_email_data_request_schema,
    user_update_password_schema_load_json,
    user_update_schema_load_json,
)
from app.user.users_schema import (
    post_send_user_email_code_schema,
    post_send_user_sms_code_schema,
    post_set_permissions_schema,
    post_verify_code_schema,
    post_verify_webauthn_schema,
)
from app.utils import url_with_token

user_blueprint = Blueprint("user", __name__)
register_errors(user_blueprint)


@user_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the auth type/mobile number check constraint
    """
    if "ck_user_has_mobile_or_other_auth" in str(exc):
        # we don't expect this to trip, so still log error
        current_app.logger.exception("Check constraint ck_user_has_mobile_or_other_auth triggered")
        return jsonify(result="error", message="Mobile number must be set if auth_type is set to sms_auth"), 400

    raise exc


@user_blueprint.route("", methods=["POST"])
def create_user():
    req_json = request.get_json()
    user_to_create = create_user_schema.load(req_json)

    save_model_user(user_to_create, password=req_json.get("password"), validated_email_access=True)
    result = user_to_create.serialize()
    return jsonify(data=result), 201


@user_blueprint.route("/<uuid:user_id>", methods=["POST"])
def update_user_attribute(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    if "updated_by" in req_json:
        updated_by = get_user_by_id(user_id=req_json.pop("updated_by"))
    else:
        updated_by = None

    update_dct = user_update_schema_load_json.load(req_json)

    save_user_attribute(user_to_update, update_dict=update_dct)
    notification = {}
    if updated_by:
        if "email_address" in update_dct:
            notification["type"] = EMAIL_TYPE
            notification["template_id"] = current_app.config["TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID"]
            notification["recipient"] = user_to_update.email_address
            notification["reply_to"] = current_app.config["EAS_EMAIL_REPLY_TO_ID"]
        elif "mobile_number" in update_dct:
            notification["type"] = SMS_TYPE
            notification["template_id"] = current_app.config["TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID"]
            notification["recipient"] = user_to_update.mobile_number
        else:
            return jsonify(data=user_to_update.serialize()), 200

        notification["personalisation"] = {
            "name": user_to_update.name,
            "servicemanagername": updated_by.name,
            "email address": user_to_update.email_address,
        }

        notify_send(notification)

    return jsonify(data=user_to_update.serialize()), 200


@user_blueprint.route("/<uuid:user_id>/archive", methods=["POST"])
def archive_user(user_id):
    user = get_user_by_id(user_id)
    dao_archive_user(user)

    return "", 204


@user_blueprint.route("/<uuid:user_id>/activate", methods=["POST"])
def activate_user(user_id):
    user = get_user_by_id(user_id=user_id)
    if user.state == "active":
        raise InvalidRequest("User already active", status_code=400)

    user.state = "active"
    save_model_user(user)
    return jsonify(data=user.serialize()), 200


@user_blueprint.route("/<uuid:user_id>/reset-failed-login-count", methods=["POST"])
def user_reset_failed_login_count(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    reset_failed_login_count(user_to_update)
    return jsonify(data=user_to_update.serialize()), 200


@user_blueprint.route("/<uuid:user_id>/verify/password", methods=["POST"])
def verify_user_password(user_id):
    user_to_verify = get_user_by_id(user_id=user_id)

    try:
        txt_pwd = request.get_json()["password"]
    except KeyError:
        message = "Required field missing data"
        errors = {"password": [message]}
        raise InvalidRequest(errors, status_code=400)

    if user_to_verify.check_password(txt_pwd):
        reset_failed_login_count(user_to_verify)
        return jsonify({}), 204
    else:
        increment_failed_login_count(user_to_verify)
        message = "Incorrect password"
        errors = {"password": [message]}
        raise InvalidRequest(errors, status_code=400)


@user_blueprint.route("/<uuid:user_id>/verify/code", methods=["POST"])
def verify_user_code(user_id):
    data = request.get_json()
    validate(data, post_verify_code_schema)

    user_to_verify = get_user_by_id(user_id=user_id)

    code = get_user_code(user_to_verify, data["code"], data["code_type"])
    if user_to_verify.failed_login_count >= current_app.config.get("MAX_FAILED_LOGIN_COUNT"):
        raise InvalidRequest("Code not found", status_code=404)
    if not code:
        # only relevant from sms
        increment_failed_login_count(user_to_verify)
        raise InvalidRequest("Code not found", status_code=404)
    if datetime.utcnow() > code.expiry_datetime or code.code_used:
        # sms and email
        increment_failed_login_count(user_to_verify)
        raise InvalidRequest("Code has expired", status_code=400)

    user_to_verify.current_session_id = str(uuid.uuid4())
    user_to_verify.logged_in_at = datetime.utcnow()
    if data["code_type"] == "email":
        user_to_verify.email_access_validated_at = datetime.utcnow()
    user_to_verify.failed_login_count = 0
    save_model_user(user_to_verify)

    use_user_code(code.id)
    return jsonify({}), 204


# TODO: Remove the "verify" endpoint once admin no longer points at it
@user_blueprint.route("/<uuid:user_id>/complete/webauthn-login", methods=["POST"])
@user_blueprint.route("/<uuid:user_id>/verify/webauthn-login", methods=["POST"])
def complete_login_after_webauthn_authentication_attempt(user_id):
    """
    complete login after a webauthn authentication. There's nothing webauthn specific in this code
    but the sms/email flows do this as part of `verify_user_code` above and this is the equivalent spot in the
    webauthn flow.

    If the authentication was successful, we've already confirmed the user holds the right security key,
    but we still need to check the max login count and set up a current_session_id and last_logged_in_at here.

    If the authentication was unsuccessful then we just bump the failed_login_count in the db.
    """
    data = request.get_json()
    validate(data, post_verify_webauthn_schema)

    user = get_user_by_id(user_id=user_id)
    successful = data["successful"]

    if user.failed_login_count >= current_app.config.get("MAX_VERIFY_CODE_COUNT"):
        raise InvalidRequest("Maximum login count exceeded", status_code=403)

    if successful:
        user.current_session_id = str(uuid.uuid4())
        user.logged_in_at = datetime.utcnow()
        user.failed_login_count = 0
        save_model_user(user)

        if webauthn_credential_id := data.get("webauthn_credential_id"):
            webauthn_credential = dao_get_webauthn_credential_by_user_and_id(user_id, webauthn_credential_id)
            dao_update_webauthn_credential_logged_in_at(webauthn_credential)
    else:
        increment_failed_login_count(user)

    return jsonify({}), 204


@user_blueprint.route("/<uuid:user_id>/<code_type>-code", methods=["POST"])
def send_user_2fa_code(user_id, code_type):
    user_to_send_to = get_user_by_id(user_id=user_id)

    if count_user_verify_codes(user_to_send_to) >= current_app.config.get("MAX_VERIFY_CODE_COUNT"):
        # Prevent more than `MAX_VERIFY_CODE_COUNT` active verify codes at a time
        current_app.logger.warning("Too many verify codes created for user {}".format(user_to_send_to.id))
    else:
        data = request.get_json()
        current_app.logger.info(data)
        if code_type == SMS_TYPE:
            validate(data, post_send_user_sms_code_schema)
            send_user_sms_code(user_to_send_to, data)
        elif code_type == EMAIL_TYPE:
            validate(data, post_send_user_email_code_schema)
            send_user_email_code(user_to_send_to, data)
        else:
            abort(404)

    return "{}", 204


def send_user_sms_code(user_to_send_to, data):
    recipient = data.get("to") or user_to_send_to.mobile_number

    secret_code = create_secret_code()
    personalisation = {"verify_code": secret_code}

    create_2fa_code(
        current_app.config["SMS_CODE_TEMPLATE_ID"], SMS_TYPE, user_to_send_to, secret_code, recipient, personalisation
    )


def send_user_email_code(user_to_send_to, data):
    recipient = user_to_send_to.email_address

    secret_code = str(uuid.uuid4())
    personalisation = {
        "name": user_to_send_to.name,
        "url": _create_2fa_url(user_to_send_to, secret_code, data.get("next"), data.get("email_auth_link_host")),
    }

    create_2fa_code(
        current_app.config["EMAIL_2FA_TEMPLATE_ID"],
        EMAIL_TYPE,
        user_to_send_to,
        secret_code,
        recipient,
        personalisation,
    )


def create_2fa_code(template_id, code_type, user_to_send_to, secret_code, recipient, personalisation):
    current_app.logger.info(f"Create_2fa_code for template {template_id}")

    # save the code in the VerifyCode table
    create_user_code(user_to_send_to, secret_code, code_type)

    notification = {
        "type": code_type,
        "template_id": template_id,
        "recipient": recipient,
        "personalisation": personalisation,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"] if code_type == EMAIL_TYPE else None
    }

    response = notify_send(notification)

    if response is HTTPError:
        current_app.logger.error(response)
    current_app.logger.info(response)


@user_blueprint.route("/<uuid:user_id>/change-email-verification", methods=["POST"])
def send_user_confirm_new_email(user_id):
    user_to_send_to = get_user_by_id(user_id=user_id)
    email = email_data_request_schema.load(request.get_json())

    notification = {
        "type": EMAIL_TYPE,
        "template_id": current_app.config["CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID"],
        "recipient": email,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "name": user_to_send_to.name,
            "url": _create_confirmation_url(user=user_to_send_to, email_address=email["email"]),
            "feedback_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/support",
        },
    }

    notify_send(notification)

    return jsonify({}), 204


@user_blueprint.route("/<uuid:user_id>/email-verification", methods=["POST"])
def send_new_user_email_verification(user_id):
    request_json = request.get_json()

    # when registering, we verify all users' email addresses using this function
    user_to_send_to = get_user_by_id(user_id=user_id)

    notification = {
        "type": EMAIL_TYPE,
        "template_id": current_app.config["NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID"],
        "recipient": user_to_send_to.email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "name": user_to_send_to.name,
            "url": _create_verification_url(
                user_to_send_to,
                base_url=request_json.get("admin_base_url"),
            ),
        },
    }

    notify_send(notification)

    return jsonify({}), 204


@user_blueprint.route("/<uuid:user_id>/email-already-registered", methods=["POST"])
def send_already_registered_email(user_id):
    to = email_data_request_schema.load(request.get_json())

    notification = {
        "type": EMAIL_TYPE,
        "template_id": current_app.config["ALREADY_REGISTERED_EMAIL_TEMPLATE_ID"],
        "recipient": to["email"],
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "signin_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/sign-in",
            "forgot_password_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/forgot-password",
            "feedback_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/support",
        }
    }

    notify_send(notification)

    return jsonify({}), 204


@user_blueprint.route("/<uuid:user_id>", methods=["GET"])
@user_blueprint.route("", methods=["GET"])
def get_user(user_id=None):
    users = get_user_by_id(user_id=user_id)
    result = [x.serialize() for x in users] if isinstance(users, list) else users.serialize()
    return jsonify(data=result)


@user_blueprint.route("/<uuid:user_id>/service/<uuid:service_id>/permission", methods=["POST"])
def set_permissions(user_id, service_id):
    # TODO fix security hole, how do we verify that the user
    # who is making this request has permission to make the request.
    service_user = dao_get_service_user(user_id, service_id)
    user = get_user_by_id(user_id)
    service = dao_fetch_service_by_id(service_id=service_id)

    data = request.get_json()
    validate(data, post_set_permissions_schema)

    permission_list = [
        Permission(service_id=service_id, user_id=user_id, permission=p["permission"]) for p in data["permissions"]
    ]

    permission_dao.set_user_service_permission(user, service, permission_list, _commit=True, replace=True)

    if "folder_permissions" in data:
        folders = [
            dao_get_template_folder_by_id_and_service_id(folder_id, service_id)
            for folder_id in data["folder_permissions"]
        ]

        service_user.folders = folders
        dao_update_service_user(service_user)

    return jsonify({}), 204


@user_blueprint.route("/email", methods=["POST"])
def fetch_user_by_email():
    email = email_data_request_schema.load(request.get_json())

    fetched_user = get_user_by_email(email["email"])
    result = fetched_user.serialize()
    return jsonify(data=result)


# TODO: Deprecate this GET endpoint
@user_blueprint.route("/email", methods=["GET"])
def get_by_email():
    email = request.args.get("email")
    if not email:
        error = "Invalid request. Email query string param required"
        raise InvalidRequest(error, status_code=400)
    fetched_user = get_user_by_email(email)
    result = fetched_user.serialize()
    return jsonify(data=result)


@user_blueprint.route("/find-users-by-email", methods=["POST"])
def find_users_by_email():
    email = partial_email_data_request_schema.load(request.get_json())

    fetched_users = get_users_by_partial_email(email["email"])
    result = [user.serialize_for_users_list() for user in fetched_users]
    return jsonify(data=result), 200


@user_blueprint.route("/reset-password", methods=["POST"])
def send_user_reset_password():
    request_json = request.get_json()
    data = email_data_request_schema.load(request_json)
    user_to_send_to = get_user_by_email(data["email"])

    print(user_to_send_to)

    notification = {
        "type": EMAIL_TYPE,
        "template_id": current_app.config["PASSWORD_RESET_TEMPLATE_ID"],
        "recipient": data["email"],
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "user_name": user_to_send_to.name,
            "url": _create_reset_password_url(
                user_to_send_to.email_address,
                base_url=request_json.get("admin_base_url"),
                next_redirect=request_json.get("next"),
            ),
        },
    }

    notify_send(notification)

    return jsonify({}), 204


@user_blueprint.route("/<uuid:user_id>/update-password", methods=["POST"])
def update_password(user_id):
    user = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    password = req_json.get("_password")

    user_update_password_schema_load_json.load(req_json)

    update_user_password(user, password)
    return jsonify(data=user.serialize()), 200


@user_blueprint.route("/<uuid:user_id>/organisations-and-services", methods=["GET"])
def get_organisations_and_services_for_user(user_id):
    user = get_user_and_accounts(user_id)
    data = get_orgs_and_services(user)
    return jsonify(data)


def _create_reset_password_url(email, next_redirect, base_url=None):
    data = json.dumps({"email": email, "created_at": str(datetime.utcnow())})
    static_url_part = "/new-password/"
    full_url = url_with_token(data, static_url_part, current_app.config, base_url=base_url)
    if next_redirect:
        full_url += "?{}".format(urlencode({"next": next_redirect}))
    return full_url


def _create_verification_url(user, base_url):
    data = json.dumps({"user_id": str(user.id), "email": user.email_address})
    url = "/verify-email/"
    return url_with_token(data, url, current_app.config, base_url=base_url)


def _create_confirmation_url(user, email_address):
    data = json.dumps({"user_id": str(user.id), "email": email_address})
    url = "/user-profile/email/confirm/"
    return url_with_token(data, url, current_app.config)


def _create_2fa_url(user, secret_code, next_redirect, email_auth_link_host):
    data = json.dumps({"user_id": str(user.id), "secret_code": secret_code})
    url = "/email-auth/"
    full_url = url_with_token(data, url, current_app.config, base_url=email_auth_link_host)
    if next_redirect:
        full_url += "?{}".format(urlencode({"next": next_redirect}))
    return full_url


def get_orgs_and_services(user):
    return {
        "organisations": [
            {
                "name": org.name,
                "id": org.id,
                "count_of_live_services": len(org.live_services),
            }
            for org in user.organisations
            if org.active
        ],
        "services": [
            {
                "id": service.id,
                "name": service.name,
                "restricted": service.restricted,
                "organisation": service.organisation.id if service.organisation else None,
            }
            for service in user.services
            if service.active
        ],
    }
