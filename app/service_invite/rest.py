from emergency_alerts_utils.url_safe_token import check_token, generate_token
from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadData, SignatureExpired

from app.clients.notify_client import notify_send
from app.dao.invited_user_dao import (
    get_invited_user_by_id,
    get_invited_user_by_service_and_id,
    get_invited_users_for_service,
    save_invited_user,
)
from app.errors import InvalidRequest, register_errors
from app.models import EMAIL_TYPE
from app.schemas import invited_user_schema
from app.utils import log_user

service_invite = Blueprint("service_invite", __name__)

register_errors(service_invite)


@service_invite.route("/service/<service_id>/invite", methods=["POST"])
def create_invited_user(service_id):
    request_json = request.get_json()
    invited_user = invited_user_schema.load(request_json)
    save_invited_user(invited_user)
    log_user(invited_user.serialize(), "User invited")

    notification = {
        "type": EMAIL_TYPE,
        "template_id": current_app.config["BROADCAST_INVITATION_EMAIL_TEMPLATE_ID"],
        "recipient": invited_user.email_address,
        "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"],
        "personalisation": {
            "user_name": invited_user.from_user.name,
            "service_name": invited_user.service.name,
            "url": invited_user_url(
                invited_user.id,
                request_json.get("invite_link_host"),
            ),
        },
    }

    notify_send(notification)

    return jsonify(data=invited_user_schema.dump(invited_user)), 201


@service_invite.route("/service/<service_id>/invite", methods=["GET"])
def get_invited_users_by_service(service_id):
    invited_users = get_invited_users_for_service(service_id)
    return jsonify(data=invited_user_schema.dump(invited_users, many=True)), 200


@service_invite.route("/service/<service_id>/invite/<invited_user_id>", methods=["GET"])
def get_invited_user_by_service(service_id, invited_user_id):
    invited_user = get_invited_user_by_service_and_id(service_id, invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200


@service_invite.route("/service/<service_id>/invite/<invited_user_id>", methods=["POST"])
def update_invited_user(service_id, invited_user_id):
    fetched = get_invited_user_by_service_and_id(service_id=service_id, invited_user_id=invited_user_id)

    current_data = dict(invited_user_schema.dump(fetched).items())
    current_data.update(request.get_json())
    update_dict = invited_user_schema.load(current_data)
    save_invited_user(update_dict)
    return jsonify(data=invited_user_schema.dump(fetched)), 200


def invited_user_url(invited_user_id, invite_link_host=None):
    token = generate_token(str(invited_user_id), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"])

    if invite_link_host is None:
        invite_link_host = current_app.config["ADMIN_EXTERNAL_URL"]

    print("test")
    return "{0}/invitation/{1}".format(invite_link_host, token)


@service_invite.route("/invite/service/<uuid:invited_user_id>", methods=["GET"])
def get_invited_user(invited_user_id):
    invited_user = get_invited_user_by_id(invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200


@service_invite.route("/invite/service/<token>", methods=["GET"])
@service_invite.route("/invite/service/check/<token>", methods=["GET"])
def validate_service_invitation_token(token):
    max_age_seconds = 60 * 60 * 24 * current_app.config["INVITATION_EXPIRATION_DAYS"]

    try:
        invited_user_id = check_token(
            token, current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"], max_age_seconds
        )
    except SignatureExpired:
        errors = {
            "invitation": "Your invitation to GOV.UK Notify has expired. "
            "Please ask the person that invited you to send you another one"
        }
        raise InvalidRequest(errors, status_code=400)
    except BadData:
        errors = {"invitation": "Something’s wrong with this link. Make sure you’ve copied the whole thing."}
        raise InvalidRequest(errors, status_code=400)

    invited_user = get_invited_user_by_id(invited_user_id)
    return jsonify(data=invited_user_schema.dump(invited_user)), 200
