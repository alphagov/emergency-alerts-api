from flask import Blueprint, current_app, jsonify, request
from itsdangerous import BadData, SignatureExpired
from emergency_alerts_utils.url_safe_token import check_token, generate_token

from app.config import QueueNames
from app.dao.invited_org_user_dao import (
    get_invited_org_user as dao_get_invited_org_user,
)
from app.dao.invited_org_user_dao import (
    get_invited_org_user_by_id,
    get_invited_org_users_for_organisation,
    save_invited_org_user,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.errors import InvalidRequest, register_errors
from app.models import EMAIL_TYPE, KEY_TYPE_NORMAL, InvitedOrganisationUser
from app.notifications.process_notifications import (
    persist_notification,
    send_notification_to_queue,
)
from app.organisation.organisation_schema import (
    post_create_invited_org_user_status_schema,
    post_update_invited_org_user_status_schema,
)
from app.schema_validation import validate

organisation_invite_blueprint = Blueprint("organisation_invite", __name__)

register_errors(organisation_invite_blueprint)


@organisation_invite_blueprint.route("/organisation/<uuid:organisation_id>/invite", methods=["POST"])
def invite_user_to_org(organisation_id):
    data = request.get_json()
    validate(data, post_create_invited_org_user_status_schema)

    invited_org_user = InvitedOrganisationUser(
        email_address=data["email_address"], invited_by_id=data["invited_by"], organisation_id=organisation_id
    )
    save_invited_org_user(invited_org_user)

    template = dao_get_template_by_id(current_app.config["ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID"])

    saved_notification = persist_notification(
        template_id=template.id,
        template_version=template.version,
        recipient=invited_org_user.email_address,
        service=template.service,
        personalisation={
            "user_name": (
                "The GOV.UK Notify team"
                if invited_org_user.invited_by.platform_admin
                else invited_org_user.invited_by.name
            ),
            "organisation_name": invited_org_user.organisation.name,
            "url": invited_org_user_url(
                invited_org_user.id,
                data.get("invite_link_host"),
            ),
        },
        notification_type=EMAIL_TYPE,
        api_key_id=None,
        key_type=KEY_TYPE_NORMAL,
        reply_to_text=invited_org_user.invited_by.email_address,
    )

    send_notification_to_queue(saved_notification, research_mode=False, queue=QueueNames.NOTIFY)

    return jsonify(data=invited_org_user.serialize()), 201


@organisation_invite_blueprint.route("/organisation/<uuid:organisation_id>/invite", methods=["GET"])
def get_invited_org_users_by_organisation(organisation_id):
    invited_org_users = get_invited_org_users_for_organisation(organisation_id)
    return jsonify(data=[x.serialize() for x in invited_org_users]), 200


@organisation_invite_blueprint.route(
    "/organisation/<uuid:organisation_id>/invite/<invited_org_user_id>", methods=["GET"]
)
def get_invited_org_user_by_organisation(organisation_id, invited_org_user_id):
    invited_org_user = dao_get_invited_org_user(organisation_id, invited_org_user_id)
    return jsonify(data=invited_org_user.serialize()), 200


@organisation_invite_blueprint.route(
    "/organisation/<uuid:organisation_id>/invite/<invited_org_user_id>", methods=["POST"]
)
def update_org_invite_status(organisation_id, invited_org_user_id):
    fetched = dao_get_invited_org_user(organisation_id=organisation_id, invited_org_user_id=invited_org_user_id)

    data = request.get_json()
    validate(data, post_update_invited_org_user_status_schema)

    fetched.status = data["status"]
    save_invited_org_user(fetched)

    return jsonify(data=fetched.serialize()), 200


def invited_org_user_url(invited_org_user_id, invite_link_host=None):
    token = generate_token(
        str(invited_org_user_id), current_app.config["SECRET_KEY"], current_app.config["DANGEROUS_SALT"]
    )

    if invite_link_host is None:
        invite_link_host = current_app.config["ADMIN_BASE_URL"]

    return "{0}/organisation-invitation/{1}".format(invite_link_host, token)


@organisation_invite_blueprint.route("/invite/organisation/<uuid:invited_org_user_id>", methods=["GET"])
def get_invited_org_user(invited_org_user_id):
    invited_user = get_invited_org_user_by_id(invited_org_user_id)
    return jsonify(data=invited_user.serialize()), 200


@organisation_invite_blueprint.route("/invite/organisation/<token>", methods=["GET"])
@organisation_invite_blueprint.route("/invite/organisation/check/<token>", methods=["GET"])
def validate_invitation_token(token):

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

    invited_user = get_invited_org_user_by_id(invited_user_id)
    return jsonify(data=invited_user.serialize()), 200
