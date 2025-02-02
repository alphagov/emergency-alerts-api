from sqlalchemy.sql.expression import func

from app import db
from app.dao.dao_utils import VersionOptions, autocommit, version_class
from app.models import Domain, Organisation, Service, User
from app.utils import get_archived_db_column_value


def dao_get_organisations():
    return Organisation.query.order_by(Organisation.active.desc(), Organisation.name.asc()).all()


def dao_count_organisations_with_live_services():
    return (
        db.session.query(Organisation.id)
        .join(Organisation.services)
        .filter(
            Service.active.is_(True),
            Service.restricted.is_(False),
        )
        .distinct()
        .count()
    )


def dao_get_organisation_services(organisation_id):
    return Organisation.query.filter_by(id=organisation_id).one().services


def dao_get_organisation_by_id(organisation_id):
    return Organisation.query.filter_by(id=organisation_id).one()


def dao_get_organisation_by_email_address(email_address):
    email_address = email_address.lower().replace(".gsi.gov.uk", ".gov.uk")

    for domain in Domain.query.order_by(func.char_length(Domain.domain).desc()).all():
        if email_address.endswith("@{}".format(domain.domain)) or email_address.endswith(".{}".format(domain.domain)):
            return Organisation.query.filter_by(id=domain.organisation_id).one()

    return None


def dao_get_organisation_by_service_id(service_id):
    return Organisation.query.join(Organisation.services).filter_by(id=service_id).first()


@autocommit
def dao_create_organisation(organisation):
    db.session.add(organisation)
    db.session.commit()


@autocommit
def dao_update_organisation(organisation_id, **kwargs):
    domains = kwargs.pop("domains", None)

    num_updated = Organisation.query.filter_by(id=organisation_id).update(kwargs)

    if isinstance(domains, list):
        Domain.query.filter_by(organisation_id=organisation_id).delete()

        db.session.bulk_save_objects(
            [Domain(domain=domain.lower(), organisation_id=organisation_id) for domain in domains]
        )

    organisation = Organisation.query.get(organisation_id)

    if "organisation_type" in kwargs:
        _update_organisation_services(organisation, "organisation_type", only_where_none=False)

    if "crown" in kwargs:
        _update_organisation_services(organisation, "crown", only_where_none=False)

    return num_updated


@version_class(
    VersionOptions(Service, must_write_history=False),
)
def _update_organisation_services(organisation, attribute, only_where_none=True):
    for service in organisation.services:
        if getattr(service, attribute) is None or not only_where_none:
            setattr(service, attribute, getattr(organisation, attribute))
        db.session.add(service)


@autocommit
def dao_archive_organisation(organisation_id):
    organisation = dao_get_organisation_by_id(organisation_id)

    Domain.query.filter_by(organisation_id=organisation_id).delete()

    organisation.name = get_archived_db_column_value(organisation.name)
    organisation.active = False

    db.session.add(organisation)


@autocommit
@version_class(Service)
def dao_add_service_to_organisation(service, organisation_id):
    organisation = Organisation.query.filter_by(id=organisation_id).one()

    service.organisation_id = organisation_id
    service.organisation_type = organisation.organisation_type
    service.crown = organisation.crown

    db.session.add(service)


def dao_get_users_for_organisation(organisation_id):
    return (
        db.session.query(User)
        .join(User.organisations)
        .filter(Organisation.id == organisation_id, User.state == "active")
        .order_by(User.created_at)
        .all()
    )


@autocommit
def dao_add_user_to_organisation(organisation_id, user_id):
    organisation = dao_get_organisation_by_id(organisation_id)
    user = User.query.filter_by(id=user_id).one()
    user.organisations.append(organisation)
    db.session.add(organisation)
    return user


@autocommit
def dao_remove_user_from_organisation(organisation, user):
    organisation.users.remove(user)
