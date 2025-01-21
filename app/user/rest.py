import json
import uuid
from datetime import datetime
from urllib.parse import urlencode

import pwdpy
from flask import Blueprint, abort, current_app, jsonify, request
from notifications_python_client.errors import HTTPError
from sqlalchemy.exc import IntegrityError

from app.clients.notify_client import notify_send
from app.common_passwords.rest import is_password_common
from app.dao.invited_user_dao import get_invited_user_by_email
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
    is_email_in_db,
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
from app.failed_logins.rest import (
    add_failed_login_for_requester,
    check_throttle_for_requester,
)
from app.models import EMAIL_AUTH_TYPE, EMAIL_TYPE, SMS_TYPE, Permission
from app.password_history.rest import (
    add_old_password_for_user,
    has_user_already_used_password,
)
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
from app.user.utils import (
    send_security_change_email,
    send_security_change_sms,
    validate_field,
)
from app.utils import is_local_host, log_auth_activity, log_user, url_with_token

user_blueprint = Blueprint("user", __name__)
register_errors(user_blueprint)


@user_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the auth type/mobile number check constraint
    """
    if "ck_user_has_mobile_or_other_auth" in str(exc):
        # we don't expect this to trip, so still log error
        current_app.logger.exception(
            "Check constraint ck_user_has_mobile_or_other_auth triggered", extra={"python_module": __name__}
        )
        return jsonify(result="error", message="Mobile number must be set if auth_type is set to sms_auth"), 400

    raise exc


@user_blueprint.route("", methods=["POST"])
def create_user():
    req_json = request.get_json()
    user_to_create = create_user_schema.load(req_json)

    save_model_user(user_to_create, password=req_json.get("password"), validated_email_access=True)
    result = user_to_create.serialize()
    log_user(result, "User created")
    add_old_password_for_user(user_to_create.id, password=req_json.get("password"))
    return jsonify(data=result), 201


@user_blueprint.route("/<uuid:user_id>", methods=["POST"])
def update_user_attribute(user_id):
    user_to_update = get_user_by_id(user_id=user_id)
    req_json = request.get_json()
    if "updated_by" in req_json:
        updated_by = get_user_by_id(user_id=req_json.pop("updated_by"))
    else:
        updated_by = None

    existing_email_address = user_to_update.email_address
    existing_mobile_number = user_to_update.mobile_number

    updated_name = req_json.get("name")
    updated_mobile_number = req_json.get("mobile_number")
    updated_email_address = req_json.get("email_address")

    fields = [
        ("email_address", updated_email_address, existing_email_address),
        ("mobile_number", updated_mobile_number, existing_mobile_number),
        ("name", updated_name, user_to_update.name),
    ]
    for field, updated_value, current_value in fields:
        if (
            not (
                (field == "mobile_number" and user_to_update.auth_type == EMAIL_AUTH_TYPE)
                or ((field == "mobile_number" and req_json.get("auth_type") == EMAIL_AUTH_TYPE))
            )
            and field in req_json
        ):
            if error_response := validate_field(field, current_value, updated_value, req_json, field.replace("_", " ")):
                return error_response

    # Check email not already in db
    if updated_email_address and is_email_in_db(updated_email_address):
        return (
            jsonify({"errors": ["Email address is already in use"]}),
            400,
        )

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
    elif any(measure in req_json for measure in ["name", "email_address", "mobile_number"]):
        security_measure = ""
        if "email_address" in update_dct and updated_email_address:
            security_measure = "email address"
            # Sending notification to previous email address
            send_security_change_email(
                current_app.config["SECURITY_INFO_CHANGE_EMAIL_TEMPLATE_ID"],
                user_to_update.email_address,
                current_app.config["EAS_EMAIL_REPLY_TO_ID"],
                user_to_update.name,
                "email address",
            )
        elif "mobile_number" in update_dct and updated_mobile_number:
            security_measure = "mobile number"
            # Sending notification to updated mobile number
            send_security_change_sms(user_to_update.mobile_number, "this phone")
            # Sending notification to previous mobile number
            if existing_mobile_number:
                send_security_change_sms(existing_mobile_number, "the requested phone")
        elif "name" in update_dct:
            security_measure = "name"

        # Sending notification to previous/unchanged email address
        if security_measure in {"name", "mobile number", "email address"}:
            send_security_change_email(
                current_app.config["SECURITY_INFO_CHANGE_EMAIL_TEMPLATE_ID"],
                existing_email_address,
                current_app.config["EAS_EMAIL_REPLY_TO_ID"],
                updated_name or user_to_update.name,
                security_measure,
            )

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
    check_throttle_for_requester()
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
        log_auth_activity(user_to_verify, "Failed login")
        add_failed_login_for_requester()
        message = "Incorrect password"
        errors = {"password": [message]}
        raise InvalidRequest(errors, status_code=400)


@user_blueprint.route("/<uuid:user_id>/verify/code", methods=["POST"])
def verify_user_code(user_id):
    check_throttle_for_requester()
    data = request.get_json()
    validate(data, post_verify_code_schema)

    user_to_verify = get_user_by_id(user_id=user_id)

    code = get_user_code(user_to_verify, data["code"], data["code_type"])
    if user_to_verify.failed_login_count >= current_app.config.get("MAX_FAILED_LOGIN_COUNT"):
        raise InvalidRequest("Code not found", status_code=404)
    if not code:
        # only relevant from sms
        add_failed_login_for_requester()
        increment_failed_login_count(user_to_verify)
        log_auth_activity(user_to_verify, "Failed login")
        raise InvalidRequest("Code not found", status_code=404)
    if datetime.utcnow() > code.expiry_datetime or code.code_used:
        # sms and email
        add_failed_login_for_requester()
        increment_failed_login_count(user_to_verify)
        log_auth_activity(user_to_verify, "Failed login")
        raise InvalidRequest("Code has expired", status_code=400)

    user_to_verify.current_session_id = str(uuid.uuid4())
    user_to_verify.logged_in_at = datetime.utcnow()
    if data["code_type"] == "email":
        user_to_verify.email_access_validated_at = datetime.utcnow()
    user_to_verify.failed_login_count = 0
    save_model_user(user_to_verify)

    log_auth_activity(user_to_verify, "Successful login")

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

    if user.failed_login_count >= current_app.config.get("MAX_FAILED_LOGIN_COUNT"):
        raise InvalidRequest("Maximum login count exceeded", status_code=403)

    if successful:
        user.current_session_id = str(uuid.uuid4())
        user.logged_in_at = datetime.utcnow()
        user.failed_login_count = 0
        save_model_user(user)
        log_auth_activity(user, "Successful login")

        if webauthn_credential_id := data.get("webauthn_credential_id"):
            webauthn_credential = dao_get_webauthn_credential_by_user_and_id(user_id, webauthn_credential_id)
            dao_update_webauthn_credential_logged_in_at(webauthn_credential)
    else:
        increment_failed_login_count(user)
        log_auth_activity(user, "Failed login")

    return jsonify({}), 204


@user_blueprint.route("/<uuid:user_id>/<code_type>-code", methods=["POST"])
def send_user_2fa_code(user_id, code_type):
    user_to_send_to = get_user_by_id(user_id=user_id)

    if count_user_verify_codes(user_to_send_to) >= current_app.config.get("MAX_VERIFY_CODE_COUNT"):
        # Prevent more than `MAX_VERIFY_CODE_COUNT` active verify codes at a time
        current_app.logger.warning(
            "Too many verify codes created", extra={"user_id": user_to_send_to.id, "python_module": __name__}
        )
    else:
        data = request.get_json()
        if code_type == SMS_TYPE:
            validate(data, post_send_user_sms_code_schema)
            send_user_sms_code(user_to_send_to, data)
        elif code_type == EMAIL_TYPE:
            validate(data, post_send_user_email_code_schema)
            send_user_email_code(user_to_send_to, data)
        else:
            abort(404)
        current_app.logger.info("2FA code requested", extra={"request_data": data, "python_module": __name__})

    return "{}", 204


@user_blueprint.route("/<uuid:user_id>/<code_type>-code-new-auth", methods=["POST"])
def send_user_2fa_code_new_auth(user_id, code_type):
    user_to_send_to = get_user_by_id(user_id=user_id)

    if count_user_verify_codes(user_to_send_to) >= current_app.config.get("MAX_VERIFY_CODE_COUNT"):
        # Prevent more than `MAX_VERIFY_CODE_COUNT` active verify codes at a time
        current_app.logger.warning(
            "Too many verify codes created", extra={"user_id": user_to_send_to.id, "python_module": __name__}
        )
    else:
        data = request.get_json()
        if code_type == SMS_TYPE:
            validate(data, post_send_user_sms_code_schema)
            mobile_number = data["to"]
            if error_response := validate_field(
                "to", user_to_send_to.mobile_number, mobile_number, data, "mobile number"
            ):
                return error_response
            send_user_sms_code(user_to_send_to, data)
        elif code_type == EMAIL_TYPE:
            validate(data, post_send_user_email_code_schema)
            email_address = data["to"]
            if error_response := validate_field(
                "to", user_to_send_to.email_address, email_address, data, "email address"
            ):
                return error_response
            send_user_email_code(user_to_send_to, data)
        else:
            abort(404)
        current_app.logger.info("2FA code requested", extra={"request_data": data, "python_module": __name__})

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
    # save the code in the VerifyCode table
    create_user_code(user_to_send_to, secret_code, code_type)

    if is_local_host():
        print(f"Development environment 2fa code: {secret_code}")

    notification = {
        "type": code_type,
        "template_id": template_id,
        "recipient": recipient,
        "personalisation": personalisation,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"] if code_type == EMAIL_TYPE else None,
    }

    current_app.logger.info("create_2fa_code", extra={"python_module": __name__, "notification": notification})

    response = notify_send(notification)

    if response is HTTPError:
        current_app.logger.error(
            "Error sending 2FA notification", extra={"notify_response": response, "python_module": __name__}
        )
    else:
        current_app.logger.info("2FA notification sent", extra={"notify_response": response, "python_module": __name__})


@user_blueprint.route("/<uuid:user_id>/change-email-verification", methods=["POST"])
def send_user_confirm_new_email(user_id):
    user_to_send_to = get_user_by_id(user_id=user_id)
    try:
        email = email_data_request_schema.load(request.get_json())
    except Exception:
        return (
            jsonify({"errors": ["Enter a valid email address"]}),
            400,
        )
    email = email["email"]
    if email == "" or email is None:
        return (
            jsonify({"errors": ["Enter a valid email address"]}),
            400,
        )
    elif email == user_to_send_to.email_address:
        return (
            jsonify({"errors": ["Email address must be different to current email address"]}),
            400,
        )
    elif is_email_in_db(email):
        return (
            jsonify({"errors": ["Email address is already in use"]}),
            400,
        )

    notification = {
        "type": EMAIL_TYPE,
        "template_id": current_app.config["CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID"],
        "recipient": email,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "name": user_to_send_to.name,
            "url": _create_confirmation_url(user=user_to_send_to, email_address=email),
            "feedback_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/support",
        },
    }

    current_app.logger.info(
        "send_user_confirm_new_email",
        extra={
            "python_module": __name__,
            "user_id": user_id,
            "notification": notification,
        },
    )

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

    current_app.logger.info(
        "send_new_user_email_verification",
        extra={
            "python_module": __name__,
            "user_id": user_id,
            "notification": notification,
        },
    )

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
        },
    }

    current_app.logger.info(
        "send_already_registered_email",
        extra={
            "python_module": __name__,
            "user_id": user_id,
            "notification": notification,
        },
    )

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

    current_app.logger.info(
        "set_permissions",
        extra={
            "python_module": __name__,
            "user_id": user_id,
            "service_id": service_id,
            "requested_permissions": data["permissions"],
        },
    )

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
    check_throttle_for_requester()
    email = email_data_request_schema.load(request.get_json())
    try:
        fetched_user = get_user_by_email(email["email"])
    except Exception:
        if not _pending_registration(email["email"]):
            add_failed_login_for_requester()
        log_auth_activity(email["email"], "Attempted Login", admin_only=False)
        raise
    result = fetched_user.serialize()
    return jsonify(data=result)


@user_blueprint.route("/email-in-db", methods=["POST"])
def check_email_already_in_db():
    email = email_data_request_schema.load(request.get_json())
    return jsonify(is_email_in_db(email["email"]))


@user_blueprint.route("/email-in-use", methods=["POST"])
def check_email_already_in_use():
    try:
        email = email_data_request_schema.load(request.get_json())
        return jsonify(is_email_in_db(email["email"]))
    except Exception:
        return (
            jsonify({"errors": ["Enter a valid email address"]}),
            400,
        )


@user_blueprint.route("/invited", methods=["POST"])
def fetch_invited_user_by_email():
    email = email_data_request_schema.load(request.get_json())

    fetched_user = get_invited_user_by_email(email["email"])
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

    current_app.logger.info("send_user_reset_password", extra={"python_module": __name__, "notification": notification})

    notify_send(notification)

    return jsonify({}), 204


@user_blueprint.route("/<uuid:user_id>/update-password", methods=["POST"])
def update_password(user_id):
    user = get_user_by_id(user_id=user_id)
    req_json = request.get_json()

    password = req_json.get("_password")
    user_update_password_schema_load_json.load(req_json)

    if is_password_common(password):
        return (
            jsonify({"errors": ["Your password is too common. Please choose a new one."]}),
            400,
        )
    user = get_user_by_id(user_id=user_id)
    if password and (pwdpy.entropy(password) < current_app.config["MIN_ENTROPY_THRESHOLD"]):
        return (
            jsonify({"errors": ["Your password is not strong enough, try adding more words"]}),
            400,
        )
    if password and has_user_already_used_password(user_id, password):
        return jsonify({"errors": ["You've used this password before. Please choose a new one."]}), 400

    add_old_password_for_user(user_id, password)

    current_app.logger.info("update_password", extra={"python_module": __name__, "user_id": user_id})
    update_user_password(user, password)
    send_security_change_email(
        current_app.config["SECURITY_INFO_CHANGE_EMAIL_TEMPLATE_ID"],
        user.email_address,
        current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        user.name,
        "password",
    )
    return jsonify(data=user.serialize()), 200


@user_blueprint.route("/<uuid:user_id>/check-password-validity", methods=["POST"])
def check_password_is_valid(user_id):
    req_json = request.get_json()
    password = req_json.get("_password")
    if is_password_common(password):
        return (
            jsonify({"errors": ["Your password is too common. Please choose a new one."]}),
            400,
        )
    user = get_user_by_id(user_id=user_id)
    if password and (pwdpy.entropy(password) < current_app.config["MIN_ENTROPY_THRESHOLD"]):
        return (
            jsonify({"errors": ["Your password is not strong enough, try adding more words"]}),
            400,
        )
    if password and has_user_already_used_password(user_id, password):
        return jsonify({"errors": ["You've used this password before. Please choose a new one."]}), 400
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


def _pending_registration(email_address):
    user = get_invited_user_by_email(email_address)
    return user is not None and user.status == "pending"


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
