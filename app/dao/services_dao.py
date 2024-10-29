import uuid
from datetime import datetime

from sqlalchemy.orm import joinedload
from sqlalchemy.sql.expression import asc, func

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.dao.organisation_dao import dao_get_organisation_by_email_address
from app.dao.service_user_dao import dao_get_service_user
from app.dao.template_folder_dao import dao_get_valid_template_folders_by_id
from app.models import (
    BROADCAST_TYPE,
    CROWN_ORGANISATION_TYPES,
    EMAIL_TYPE,
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_SMS_TYPE,
    LETTER_TYPE,
    NON_CROWN_ORGANISATION_TYPES,
    SMS_TYPE,
    UPLOAD_LETTERS,
    AnnualBilling,
    ApiKey,
    InvitedUser,
    Organisation,
    Permission,
    Service,
    ServiceBroadcastSettings,
    ServiceEmailReplyTo,
    ServicePermission,
    ServiceUser,
    Template,
    TemplateHistory,
    TemplateRedacted,
    User,
    VerifyCode,
)
from app.utils import escape_special_characters, get_archived_db_column_value

DEFAULT_SERVICE_PERMISSIONS = [
    BROADCAST_TYPE,
    SMS_TYPE,
    EMAIL_TYPE,
    LETTER_TYPE,
    INTERNATIONAL_SMS_TYPE,
    UPLOAD_LETTERS,
    INTERNATIONAL_LETTERS,
]


def dao_fetch_all_services(only_active=False):
    query = Service.query.order_by(asc(Service.created_at)).options(joinedload("users"))

    if only_active:
        query = query.filter(Service.active)

    return query.all()


def get_services_by_partial_name(service_name):
    service_name = escape_special_characters(service_name)
    return Service.query.filter(Service.name.ilike("%{}%".format(service_name))).all()


def dao_count_live_services():
    return Service.query.filter_by(
        active=True,
        restricted=False,
        count_as_live=True,
    ).count()


def dao_fetch_service_by_id(service_id, only_active=False):
    query = Service.query.filter_by(id=service_id).options(joinedload("users"))

    if only_active:
        query = query.filter(Service.active)

    return query.one()


def dao_fetch_service_by_id_with_api_keys(service_id, only_active=False):
    query = Service.query.filter_by(id=service_id).options(joinedload("api_keys"))

    if only_active:
        query = query.filter(Service.active)

    return query.one()


def dao_fetch_all_services_by_user(user_id, only_active=False):
    query = (
        Service.query.filter(Service.users.any(id=user_id))
        .order_by(asc(Service.created_at))
        .options(joinedload("users"))
    )

    if only_active:
        query = query.filter(Service.active)

    return query.all()


def dao_fetch_all_services_created_by_user(user_id):
    query = Service.query.filter_by(created_by_id=user_id).order_by(asc(Service.created_at))

    return query.all()


@autocommit
@version_class(
    VersionOptions(ApiKey, must_write_history=False),
    VersionOptions(Service),
    VersionOptions(Template, history_class=TemplateHistory, must_write_history=False),
)
def dao_archive_service(service_id):
    # have to eager load templates and api keys so that we don't flush when we loop through them
    # to ensure that db.session still contains the models when it comes to creating history objects
    service = (
        Service.query.options(
            joinedload("templates"),
            joinedload("templates.template_redacted"),
            joinedload("api_keys"),
        )
        .filter(Service.id == service_id)
        .one()
    )

    service.active = False
    service.name = get_archived_db_column_value(service.name)
    service.email_from = get_archived_db_column_value(service.email_from)

    for template in service.templates:
        if not template.archived:
            template.archived = True

    for api_key in service.api_keys:
        if not api_key.expiry_date:
            api_key.expiry_date = datetime.utcnow()


def dao_fetch_service_by_id_and_user(service_id, user_id):
    return (
        Service.query.filter(Service.users.any(id=user_id), Service.id == service_id).options(joinedload("users")).one()
    )


@autocommit
@version_class(Service)
def dao_create_service(
    service,
    user,
    service_id=None,
    service_permissions=None,
):
    if not user:
        raise ValueError("Can't create a service without a user")

    if service_permissions is None:
        service_permissions = DEFAULT_SERVICE_PERMISSIONS

    organisation = dao_get_organisation_by_email_address(user.email_address)

    from app.dao.permissions_dao import permission_dao

    service.users.append(user)
    permission_dao.add_default_service_permissions_for_user(user, service)
    service.id = service_id or uuid.uuid4()  # must be set now so version history model can use same id
    service.active = True
    service.research_mode = False

    for permission in service_permissions:
        service_permission = ServicePermission(service_id=service.id, permission=permission)
        service.permissions.append(service_permission)

    if organisation:
        service.organisation_id = organisation.id
        service.organisation_type = organisation.organisation_type

    if organisation:
        service.crown = organisation.crown
    elif service.organisation_type in CROWN_ORGANISATION_TYPES:
        service.crown = True
    elif service.organisation_type in NON_CROWN_ORGANISATION_TYPES:
        service.crown = False
    service.count_as_live = not user.platform_admin

    db.session.add(service)


@autocommit
@version_class(Service)
def dao_update_service(service):
    db.session.add(service)


def dao_add_user_to_service(service, user, permissions=None, folder_permissions=None):
    permissions = permissions or []
    folder_permissions = folder_permissions or []

    try:
        from app.dao.permissions_dao import permission_dao

        service.users.append(user)
        permission_dao.set_user_service_permission(user, service, permissions, _commit=False)
        db.session.add(service)

        service_user = dao_get_service_user(user.id, service.id)
        valid_template_folders = dao_get_valid_template_folders_by_id(folder_permissions)
        service_user.folders = valid_template_folders
        db.session.add(service_user)

    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


def dao_remove_user_from_service(service, user):
    try:
        from app.dao.permissions_dao import permission_dao

        permission_dao.remove_user_service_permissions(user, service)

        service_user = dao_get_service_user(user.id, service.id)
        db.session.delete(service_user)
    except Exception as e:
        db.session.rollback()
        raise e
    else:
        db.session.commit()


@autocommit
def delete_service_and_all_associated_db_objects(service):
    def _delete(query):
        query.delete(synchronize_session=False)

    template_ids = db.session.query(Template.id).filter_by(service=service)
    _delete(TemplateRedacted.query.filter(TemplateRedacted.template_id.in_(template_ids)))

    _delete(ServiceEmailReplyTo.query.filter_by(service=service))
    _delete(InvitedUser.query.filter_by(service=service))
    _delete(Permission.query.filter_by(service=service))
    _delete(Template.query.filter_by(service=service))
    _delete(TemplateHistory.query.filter_by(service_id=service.id))
    _delete(ServicePermission.query.filter_by(service_id=service.id))
    _delete(ApiKey.query.filter_by(service=service))
    _delete(ApiKey.get_history_model().query.filter_by(service_id=service.id))
    _delete(AnnualBilling.query.filter_by(service_id=service.id))

    verify_codes = VerifyCode.query.join(User).filter(User.id.in_([x.id for x in service.users]))
    list(map(db.session.delete, verify_codes))

    created_by_id = Service.query.filter_by(id=service.id).one().created_by_id
    users = [x for x in service.users]
    for user in users:
        if user.id != created_by_id:
            user.organisations = []
            service.users.remove(user)

    _delete(Service.get_history_model().query.filter_by(id=service.id))

    db.session.delete(service)

    for user in users:
        if user.id != created_by_id:
            db.session.delete(user)


def delete_service_created_for_functional_testing(service):
    def _delete(query):
        query.delete(synchronize_session=False)

    _delete(AnnualBilling.query.filter_by(service_id=service.id))
    _delete(Permission.query.filter_by(service=service))
    _delete(ServiceBroadcastSettings.query.filter_by(service_id=service.id))
    _delete(ServicePermission.query.filter_by(service_id=service.id))
    _delete(ServiceUser.query.filter_by(service_id=service.id))
    db.session.delete(service)


def dao_fetch_active_users_for_service(service_id):
    query = User.query.filter(User.services.any(id=service_id), User.state == "active")

    return query.all()


def get_live_services_with_organisation():
    query = (
        db.session.query(
            Service.id.label("service_id"),
            Service.name.label("service_name"),
            Organisation.id.label("organisation_id"),
            Organisation.name.label("organisation_name"),
        )
        .outerjoin(Service.organisation)
        .filter(Service.count_as_live.is_(True), Service.active.is_(True), Service.restricted.is_(False))
        .order_by(Organisation.name, Service.name)
    )

    return query.all()


def fetch_billing_details_for_all_services():
    return (
        db.session.query(
            Service.id.label("service_id"),
            func.coalesce(Service.purchase_order_number, Organisation.purchase_order_number).label(
                "purchase_order_number"
            ),
            func.coalesce(Service.billing_contact_names, Organisation.billing_contact_names).label(
                "billing_contact_names"
            ),
            func.coalesce(Service.billing_contact_email_addresses, Organisation.billing_contact_email_addresses).label(
                "billing_contact_email_addresses"
            ),
            func.coalesce(Service.billing_reference, Organisation.billing_reference).label("billing_reference"),
        )
        .outerjoin(Service.organisation)
        .all()
    )
