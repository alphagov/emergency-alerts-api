from flask import Blueprint, abort, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.dao.annual_billing_dao import set_default_free_allowance_for_service
from app.dao.dao_utils import transaction
from app.dao.invited_org_user_dao import get_invited_org_users_for_organisation
from app.dao.organisation_dao import (
    dao_add_service_to_organisation,
    dao_add_user_to_organisation,
    dao_archive_organisation,
    dao_create_organisation,
    dao_get_organisation_by_email_address,
    dao_get_organisation_by_id,
    dao_get_organisation_services,
    dao_get_organisations,
    dao_get_users_for_organisation,
    dao_remove_user_from_organisation,
    dao_update_organisation,
)
from app.dao.services_dao import dao_fetch_service_by_id
from app.dao.users_dao import get_user_by_id
from app.errors import InvalidRequest, register_errors
from app.models import INVITE_PENDING, Organisation
from app.organisation.organisation_schema import (
    post_create_organisation_schema,
    post_link_service_to_organisation_schema,
    post_update_organisation_schema,
)
from app.schema_validation import validate

organisation_blueprint = Blueprint("organisation", __name__)
register_errors(organisation_blueprint)


@organisation_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint on ix_organisation_name
    """
    if "ix_organisation_name" in str(exc):
        return jsonify(result="error", message="Organisation name already exists"), 400
    if 'duplicate key value violates unique constraint "domain_pkey"' in str(exc):
        return jsonify(result="error", message="Domain already exists"), 400

    current_app.logger.exception(exc)
    return jsonify(result="error", message="Internal server error"), 500


@organisation_blueprint.route("", methods=["GET"])
def get_organisations():
    organisations = [org.serialize_for_list() for org in dao_get_organisations()]

    return jsonify(organisations)


@organisation_blueprint.route("/<uuid:organisation_id>", methods=["GET"])
def get_organisation_by_id(organisation_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    return jsonify(organisation.serialize())


@organisation_blueprint.route("/by-domain", methods=["GET"])
def get_organisation_by_domain():
    domain = request.args.get("domain")

    if not domain or "@" in domain:
        abort(400)

    organisation = dao_get_organisation_by_email_address("example@{}".format(request.args.get("domain")))

    if not organisation:
        abort(404)

    return jsonify(organisation.serialize())


@organisation_blueprint.route("", methods=["POST"])
def create_organisation():
    data = request.get_json()

    validate(data, post_create_organisation_schema)

    organisation = Organisation(**data)
    dao_create_organisation(organisation)

    return jsonify(organisation.serialize()), 201


@organisation_blueprint.route("/<uuid:organisation_id>", methods=["POST"])
def update_organisation(organisation_id):
    data = request.get_json()
    validate(data, post_update_organisation_schema)

    result = dao_update_organisation(organisation_id, **data)

    if result:
        return "", 204
    else:
        raise InvalidRequest("Organisation not found", 404)


@organisation_blueprint.route("/<uuid:organisation_id>/archive", methods=["POST"])
def archive_organisation(organisation_id):
    """
    All services must be reassigned and all team members removed before an org can be
    archived.
    When an org is archived, its email branding, letter branding and any domains are deleted.
    """

    organisation = dao_get_organisation_by_id(organisation_id)

    if organisation.services:
        raise InvalidRequest("Cannot archive an organisation with services", 400)

    pending_invited_users = [
        user for user in get_invited_org_users_for_organisation(organisation_id) if user.status == INVITE_PENDING
    ]

    if organisation.users or pending_invited_users:
        raise InvalidRequest("Cannot archive an organisation with team members or invited team members", 400)

    if organisation.active:
        dao_archive_organisation(organisation_id)

    return "", 204


@organisation_blueprint.route("/<uuid:organisation_id>/service", methods=["POST"])
def link_service_to_organisation(organisation_id):
    data = request.get_json()
    validate(data, post_link_service_to_organisation_schema)
    service = dao_fetch_service_by_id(data["service_id"])
    service.organisation = None

    with transaction():
        dao_add_service_to_organisation(service, organisation_id)
        set_default_free_allowance_for_service(service, year_start=None)

    return "", 204


@organisation_blueprint.route("/<uuid:organisation_id>/services", methods=["GET"])
def get_organisation_services(organisation_id):
    services = dao_get_organisation_services(organisation_id)
    sorted_services = sorted(services, key=lambda s: (-s.active, s.name))
    return jsonify([s.serialize_for_org_dashboard() for s in sorted_services])


@organisation_blueprint.route("/<uuid:organisation_id>/users/<uuid:user_id>", methods=["POST"])
def add_user_to_organisation(organisation_id, user_id):
    new_org_user = dao_add_user_to_organisation(organisation_id, user_id)
    return jsonify(data=new_org_user.serialize())


@organisation_blueprint.route("/<uuid:organisation_id>/users/<uuid:user_id>", methods=["DELETE"])
def remove_user_from_organisation(organisation_id, user_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    user = get_user_by_id(user_id=user_id)

    if user not in organisation.users:
        error = "User not found"
        raise InvalidRequest(error, status_code=404)

    dao_remove_user_from_organisation(organisation, user)

    return {}, 204


@organisation_blueprint.route("/<uuid:organisation_id>/users", methods=["GET"])
def get_organisation_users(organisation_id):
    org_users = dao_get_users_for_organisation(organisation_id)
    return jsonify(data=[x.serialize() for x in org_users])
