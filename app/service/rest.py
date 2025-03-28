import os

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app.dao.api_key_dao import (
    expire_api_key,
    get_model_api_keys,
    get_unsigned_secret,
    save_model_api_key,
)
from app.dao.broadcast_service_dao import set_broadcast_service_type
from app.dao.dao_utils import transaction
from app.dao.failed_logins_dao import dao_delete_all_failed_logins_for_ip
from app.dao.organisation_dao import dao_get_organisation_by_service_id
from app.dao.services_dao import (
    dao_add_user_to_service,
    dao_archive_service,
    dao_create_service,
    dao_fetch_all_services,
    dao_fetch_all_services_by_user,
    dao_fetch_all_services_created_by_user,
    dao_fetch_service_by_id,
    dao_remove_user_from_service,
    dao_update_service,
    delete_service_created_for_functional_testing,
    get_services_by_partial_name,
)
from app.dao.users_dao import (
    delete_model_user,
    delete_permissions_for_user,
    delete_user_verify_codes,
    get_user_by_id,
    get_users_by_partial_email,
)
from app.errors import InvalidRequest, register_errors
from app.models import Permission, Service
from app.schema_validation import validate
from app.schemas import api_key_schema, service_schema
from app.service.sender import send_notification_to_service_users
from app.service.service_broadcast_settings_schema import (
    service_broadcast_settings_schema,
)
from app.user.users_schema import post_set_permissions_schema
from app.utils import is_public_environment

service_blueprint = Blueprint("service", __name__)

register_errors(service_blueprint)


@service_blueprint.errorhandler(IntegrityError)
def handle_integrity_error(exc):
    """
    Handle integrity errors caused by the unique constraint on ix_organisation_name
    """
    if any(
        'duplicate key value violates unique constraint "{}"'.format(constraint) in str(exc)
        for constraint in {"services_name_key"}
    ):
        return (
            jsonify(
                result="error",
                message={"name": ["Duplicate service name '{}'".format(exc.params.get("name"))]},
            ),
            400,
        )
    current_app.logger.exception(exc)
    return jsonify(result="error", message="Internal server error"), 500


@service_blueprint.route("", methods=["GET"])
def get_services():
    only_active = request.args.get("only_active") == "True"
    user_id = request.args.get("user_id", None)

    if user_id:
        services = dao_fetch_all_services_by_user(user_id, only_active)
    else:
        services = dao_fetch_all_services(only_active)
    data = service_schema.dump(services, many=True)
    return jsonify(data=data)


@service_blueprint.route("/find-services-by-name", methods=["GET"])
def find_services_by_name():
    service_name = request.args.get("service_name")
    if not service_name:
        errors = {"service_name": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    fetched_services = get_services_by_partial_name(service_name)
    data = [service.serialize_for_org_dashboard() for service in fetched_services]
    return jsonify(data=data), 200


@service_blueprint.route("/<uuid:service_id>", methods=["GET"])
def get_service_by_id(service_id):
    fetched = dao_fetch_service_by_id(service_id)

    data = service_schema.dump(fetched)
    return jsonify(data=data)


@service_blueprint.route("", methods=["POST"])
def create_service():
    data = request.get_json()

    if not data.get("user_id"):
        errors = {"user_id": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data.pop("service_domain", None)

    # validate json with marshmallow
    service_schema.load(data)

    user = get_user_by_id(data.pop("user_id"))

    # unpack valid json into service object
    valid_service = Service.from_json(data)

    with transaction():
        dao_create_service(valid_service, user)

    return jsonify(data=service_schema.dump(valid_service)), 201


@service_blueprint.route("/<uuid:service_id>", methods=["POST"])
def update_service(service_id):
    req_json = request.get_json()
    fetched_service = dao_fetch_service_by_id(service_id)
    # Capture the status change here as Marshmallow changes this later
    service_going_live = fetched_service.restricted and not req_json.get("restricted", True)
    current_data = dict(service_schema.dump(fetched_service).items())
    current_data.update(request.get_json())

    service = service_schema.load(current_data)

    dao_update_service(service)

    if service_going_live:
        send_notification_to_service_users(
            service_id=service_id,
            template_id=current_app.config["SERVICE_NOW_LIVE_TEMPLATE_ID"],
            personalisation={
                "service_name": current_data["name"],
            },
            include_user_fields=["name"],
        )

    return jsonify(data=service_schema.dump(fetched_service)), 200


@service_blueprint.route("/<uuid:service_id>/api-key", methods=["POST"])
def create_api_key(service_id=None):
    fetched_service = dao_fetch_service_by_id(service_id=service_id)
    valid_api_key = api_key_schema.load(request.get_json())
    valid_api_key.service = fetched_service
    save_model_api_key(valid_api_key)
    unsigned_api_key = get_unsigned_secret(valid_api_key.id)
    return jsonify(data=unsigned_api_key), 201


@service_blueprint.route("/<uuid:service_id>/api-key/revoke/<uuid:api_key_id>", methods=["POST"])
def revoke_api_key(service_id, api_key_id):
    expire_api_key(service_id=service_id, api_key_id=api_key_id)
    return jsonify(), 202


@service_blueprint.route("/<uuid:service_id>/api-keys", methods=["GET"])
@service_blueprint.route("/<uuid:service_id>/api-keys/<uuid:key_id>", methods=["GET"])
def get_api_keys(service_id, key_id=None):
    dao_fetch_service_by_id(service_id=service_id)

    try:
        if key_id:
            api_keys = [get_model_api_keys(service_id=service_id, id=key_id)]
        else:
            api_keys = get_model_api_keys(service_id=service_id)
    except NoResultFound:
        error = "API key not found for id: {}".format(service_id)
        raise InvalidRequest(error, status_code=404)

    return jsonify(apiKeys=api_key_schema.dump(api_keys, many=True)), 200


@service_blueprint.route("/<uuid:service_id>/users", methods=["GET"])
def get_users_for_service(service_id):
    fetched = dao_fetch_service_by_id(service_id)
    return jsonify(data=[x.serialize() for x in fetched.users])


@service_blueprint.route("/<uuid:service_id>/users/<user_id>", methods=["POST"])
def add_user_to_service(service_id, user_id):
    service = dao_fetch_service_by_id(service_id)
    user = get_user_by_id(user_id=user_id)

    if user in service.users:
        error = "User id: {} already part of service id: {}".format(user_id, service_id)
        raise InvalidRequest(error, status_code=400)

    data = request.get_json()
    validate(data, post_set_permissions_schema)

    permissions = [
        Permission(service_id=service_id, user_id=user_id, permission=p["permission"]) for p in data["permissions"]
    ]
    folder_permissions = data.get("folder_permissions", [])

    dao_add_user_to_service(service, user, permissions, folder_permissions)
    data = service_schema.dump(service)
    return jsonify(data=data), 201


@service_blueprint.route("/<uuid:service_id>/users/<user_id>", methods=["DELETE"])
def remove_user_from_service(service_id, user_id):
    service = dao_fetch_service_by_id(service_id)
    user = get_user_by_id(user_id=user_id)
    if user not in service.users:
        error = "User not found"
        raise InvalidRequest(error, status_code=404)

    elif len(service.users) == 1:
        error = "You cannot remove the only user for a service"
        raise InvalidRequest(error, status_code=400)

    dao_remove_user_from_service(service, user)
    return jsonify({}), 204


# This is placeholder get method until more thought
# goes into how we want to fetch and view various items in history
# tables. This is so product owner can pass stories as done
@service_blueprint.route("/<uuid:service_id>/history", methods=["GET"])
def get_service_history(service_id):
    from app.models import ApiKey, Service, TemplateHistory
    from app.schemas import (
        api_key_history_schema,
        service_history_schema,
        template_history_schema,
    )

    service_history = Service.get_history_model().query.filter_by(id=service_id).all()
    service_data = service_history_schema.dump(service_history, many=True)
    api_key_history = ApiKey.get_history_model().query.filter_by(service_id=service_id).all()
    api_keys_data = api_key_history_schema.dump(api_key_history, many=True)

    template_history = TemplateHistory.query.filter_by(service_id=service_id).all()
    template_data = template_history_schema.dump(template_history, many=True)

    data = {
        "service_history": service_data,
        "api_key_history": api_keys_data,
        "template_history": template_data,
        "events": [],
    }

    return jsonify(data=data)


@service_blueprint.route("/<uuid:service_id>/archive", methods=["POST"])
def archive_service(service_id):
    """
    When a service is archived the service is made inactive, templates are archived and api keys are revoked.
    There is no coming back from this operation.
    :param service_id:
    :return:
    """
    service = dao_fetch_service_by_id(service_id)

    if service.active:
        dao_archive_service(service.id)

    return "", 204


@service_blueprint.route("/<uuid:service_id>/organisation", methods=["GET"])
def get_organisation_for_service(service_id):
    organisation = dao_get_organisation_by_service_id(service_id=service_id)
    return jsonify(organisation.serialize() if organisation else {}), 200


@service_blueprint.route("/<uuid:service_id>/set-as-broadcast-service", methods=["POST"])
def set_as_broadcast_service(service_id):
    """
    This route does the following
    - adds a service broadcast settings to define which channel broadcasts should go out on
    - removes all current service permissions and adds the broadcast service permission
    - adds the service to the broadcast organisation
    - puts the service into training mode or live mode
    - removes all permissions from current users and invited users
    """
    data = validate(request.get_json(), service_broadcast_settings_schema)
    service = dao_fetch_service_by_id(service_id)

    set_broadcast_service_type(
        service,
        service_mode=data["service_mode"],
        broadcast_channel=data["broadcast_channel"],
        provider_restriction=data["provider_restriction"],
    )

    data = service_schema.dump(service)
    return jsonify(data=data)


@service_blueprint.route("/purge-services-created/<uuid:user_id>", methods=["DELETE"])
def purge_test_services_created_by(user_id):
    if is_public_environment():
        raise InvalidRequest("Endpoint not found", status_code=404)

    try:
        services = dao_fetch_all_services_created_by_user(user_id=user_id)
        for service in services:
            delete_service_created_for_functional_testing(service=service)
    except Exception as e:
        return jsonify(result="error", message=f"Unable to purge services created by user {user_id}: {e}"), 500

    return jsonify({"message": "Successfully purged services"}), 200


@service_blueprint.route("/purge-users-created-by-tests", methods=["DELETE"])
def purge_users_created_by_tests():
    if is_public_environment():
        raise InvalidRequest("Endpoint not found", status_code=404)

    try:
        users = get_users_by_partial_email("emergency-alerts-fake-")
        for user in users:
            delete_user_verify_codes(user=user)
            delete_permissions_for_user(user=user)
            delete_model_user(user=user)
    except Exception as e:
        return jsonify(result="error", message=f"Unable to purge users created by functional tests: {e}"), 500

    return jsonify({"message": "Successfully purged users"}), 200


@service_blueprint.route("/purge-failed-logins-created-by-tests", methods=["DELETE"])
def purge_failed_logins_created_by_tests():
    if is_public_environment():
        raise InvalidRequest("Endpoint not found", status_code=404)

    try:
        functional_test_ips = os.environ.get("FUNCTIONAL_TEST_IPS", "").split(",")
        for ip in functional_test_ips:
            dao_delete_all_failed_logins_for_ip(ip)
    except Exception as e:
        return jsonify(result="error", message=f"Unable to purge failed logins created by functional tests: {e}"), 500

    return jsonify({"message": "Successfully purged failed logins"}), 200
