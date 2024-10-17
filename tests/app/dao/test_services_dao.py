import uuid
from datetime import datetime
from unittest import mock

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao.organisation_dao import dao_add_service_to_organisation
from app.dao.service_permissions_dao import (
    dao_add_service_permission,
    dao_remove_service_permission,
)
from app.dao.service_user_dao import (
    dao_get_service_user,
    dao_update_service_user,
)
from app.dao.services_dao import (
    dao_add_user_to_service,
    dao_create_service,
    dao_fetch_active_users_for_service,
    dao_fetch_all_services,
    dao_fetch_all_services_by_user,
    dao_fetch_live_services_data,
    dao_fetch_service_by_id,
    dao_remove_user_from_service,
    dao_update_service,
    delete_service_and_all_associated_db_objects,
    get_live_services_with_organisation,
    get_services_by_partial_name,
)
from app.dao.users_dao import create_user_code, save_model_user
from app.models import (
    BROADCAST_TYPE,
    EMAIL_TYPE,
    INTERNATIONAL_LETTERS,
    INTERNATIONAL_SMS_TYPE,
    LETTER_TYPE,
    SMS_TYPE,
    UPLOAD_LETTERS,
    ApiKey,
    InvitedUser,
    Organisation,
    Permission,
    Service,
    ServicePermission,
    ServiceUser,
    Template,
    TemplateHistory,
    User,
    VerifyCode,
    user_folder_permissions,
)
from tests.app.db import (
    create_annual_billing,
    create_ft_billing,
    create_invited_user,
    create_organisation,
    create_service,
    create_template,
    create_template_folder,
    create_user,
)


def test_create_service(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        organisation_type="central",
        created_by=user,
    )
    dao_create_service(service, user)
    assert Service.query.count() == 1
    service_db = Service.query.one()
    assert service_db.name == "service_name"
    assert service_db.id == service.id
    assert service_db.email_from == "email_from"
    assert service_db.research_mode is False
    assert service_db.prefix_sms is True
    assert service.active is True
    assert user in service_db.users
    assert service_db.organisation_type == "central"
    assert service_db.crown is None
    assert not service.organisation_id


def test_create_service_with_organisation(notify_db_session):
    user = create_user(email="local.authority@local-authority.gov.uk")
    organisation = create_organisation(
        name="Some local authority", organisation_type="local", domains=["local-authority.gov.uk"]
    )
    assert Service.query.count() == 0
    service = Service(
        name="service_name",
        email_from="email_from",
        message_limit=1000,
        restricted=False,
        organisation_type="central",
        created_by=user,
    )
    dao_create_service(service, user)
    assert Service.query.count() == 1
    service_db = Service.query.one()
    organisation = Organisation.query.get(organisation.id)
    assert service_db.name == "service_name"
    assert service_db.id == service.id
    assert service_db.email_from == "email_from"
    assert service_db.research_mode is False
    assert service_db.prefix_sms is True
    assert service.active is True
    assert user in service_db.users
    assert service_db.organisation_type == "local"
    assert service_db.crown is None
    assert service.organisation_id == organisation.id
    assert service.organisation == organisation


def test_cannot_create_two_services_with_same_name(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service1 = Service(
        name="service_name",
        email_from="email_from1",
        message_limit=1000,
        restricted=False,
        created_by=user,
    )

    service2 = Service(
        name="service_name", email_from="email_from2", message_limit=1000, restricted=False, created_by=user
    )
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, user)
        dao_create_service(service2, user)
    assert 'duplicate key value violates unique constraint "services_name_key"' in str(excinfo.value)


def test_cannot_create_two_services_with_same_email_from(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service1 = Service(
        name="service_name1", email_from="email_from", message_limit=1000, restricted=False, created_by=user
    )
    service2 = Service(
        name="service_name2", email_from="email_from", message_limit=1000, restricted=False, created_by=user
    )
    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service1, user)
        dao_create_service(service2, user)
    assert 'duplicate key value violates unique constraint "services_email_from_key"' in str(excinfo.value)


def test_cannot_create_service_with_no_user(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    service = Service(
        name="service_name", email_from="email_from", message_limit=1000, restricted=False, created_by=user
    )
    with pytest.raises(ValueError) as excinfo:
        dao_create_service(service, None)
    assert "Can't create a service without a user" in str(excinfo.value)


def test_should_add_user_to_service(notify_db_session):
    user = create_user()
    service = Service(
        name="service_name", email_from="email_from", message_limit=1000, restricted=False, created_by=user
    )
    dao_create_service(service, user)
    assert user in Service.query.first().users
    new_user = User(
        name="Test User",
        email_address="new_user@digital.cabinet-office.gov.uk",
        password="password",
        mobile_number="+447700900986",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users


def test_dao_add_user_to_service_sets_folder_permissions(sample_user, sample_service):
    folder_1 = create_template_folder(sample_service)
    folder_2 = create_template_folder(sample_service)

    assert not folder_1.users
    assert not folder_2.users

    folder_permissions = [str(folder_1.id), str(folder_2.id)]

    dao_add_user_to_service(sample_service, sample_user, folder_permissions=folder_permissions)

    service_user = dao_get_service_user(user_id=sample_user.id, service_id=sample_service.id)
    assert len(service_user.folders) == 2
    assert folder_1 in service_user.folders
    assert folder_2 in service_user.folders


def test_dao_add_user_to_service_ignores_folders_which_do_not_exist_when_setting_permissions(
    sample_user, sample_service, fake_uuid
):
    valid_folder = create_template_folder(sample_service)
    folder_permissions = [fake_uuid, str(valid_folder.id)]

    dao_add_user_to_service(sample_service, sample_user, folder_permissions=folder_permissions)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)

    assert service_user.folders == [valid_folder]


def test_dao_add_user_to_service_raises_error_if_adding_folder_permissions_for_a_different_service(
    sample_service,
):
    user = create_user()
    other_service = create_service(service_name="other service")
    other_service_folder = create_template_folder(other_service)
    folder_permissions = [str(other_service_folder.id)]

    assert ServiceUser.query.count() == 2

    with pytest.raises(IntegrityError) as e:
        dao_add_user_to_service(sample_service, user, folder_permissions=folder_permissions)

    db.session.rollback()
    assert 'insert or update on table "user_folder_permissions" violates foreign key constraint' in str(e.value)
    assert ServiceUser.query.count() == 2


def test_should_remove_user_from_service(notify_db_session):
    user = create_user()
    service = Service(
        name="service_name", email_from="email_from", message_limit=1000, restricted=False, created_by=user
    )
    dao_create_service(service, user)
    new_user = User(
        name="Test User",
        email_address="new_user@digital.cabinet-office.gov.uk",
        password="password",
        mobile_number="+447700900986",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service, new_user)
    assert new_user in Service.query.first().users
    dao_remove_user_from_service(service, new_user)
    assert new_user not in Service.query.first().users


def test_removing_a_user_from_a_service_deletes_their_permissions(sample_user, sample_service):
    assert len(Permission.query.all()) == 8

    dao_remove_user_from_service(sample_service, sample_user)

    assert Permission.query.all() == []


def test_removing_a_user_from_a_service_deletes_their_folder_permissions_for_that_service(sample_user, sample_service):
    tf1 = create_template_folder(sample_service)
    tf2 = create_template_folder(sample_service)

    service_2 = create_service(sample_user, service_name="other service")
    tf3 = create_template_folder(service_2)

    service_user = dao_get_service_user(sample_user.id, sample_service.id)
    service_user.folders = [tf1, tf2]
    dao_update_service_user(service_user)

    service_2_user = dao_get_service_user(sample_user.id, service_2.id)
    service_2_user.folders = [tf3]
    dao_update_service_user(service_2_user)

    dao_remove_user_from_service(sample_service, sample_user)

    user_folder_permission = db.session.query(user_folder_permissions).one()
    assert user_folder_permission.user_id == service_2_user.user_id
    assert user_folder_permission.service_id == service_2_user.service_id
    assert user_folder_permission.template_folder_id == tf3.id


def test_get_all_services(notify_db_session):
    create_service(service_name="service 1", email_from="service.1")
    assert len(dao_fetch_all_services()) == 1
    assert dao_fetch_all_services()[0].name == "service 1"

    create_service(service_name="service 2", email_from="service.2")
    assert len(dao_fetch_all_services()) == 2
    assert dao_fetch_all_services()[1].name == "service 2"


def test_get_all_services_should_return_in_created_order(notify_db_session):
    create_service(service_name="service 1", email_from="service.1")
    create_service(service_name="service 2", email_from="service.2")
    create_service(service_name="service 3", email_from="service.3")
    create_service(service_name="service 4", email_from="service.4")
    assert len(dao_fetch_all_services()) == 4
    assert dao_fetch_all_services()[0].name == "service 1"
    assert dao_fetch_all_services()[1].name == "service 2"
    assert dao_fetch_all_services()[2].name == "service 3"
    assert dao_fetch_all_services()[3].name == "service 4"


def test_get_all_services_should_return_empty_list_if_no_services():
    assert len(dao_fetch_all_services()) == 0


def test_get_all_services_for_user(notify_db_session):
    user = create_user()
    create_service(service_name="service 1", user=user, email_from="service.1")
    create_service(service_name="service 2", user=user, email_from="service.2")
    create_service(service_name="service 3", user=user, email_from="service.3")
    assert len(dao_fetch_all_services_by_user(user.id)) == 3
    assert dao_fetch_all_services_by_user(user.id)[0].name == "service 1"
    assert dao_fetch_all_services_by_user(user.id)[1].name == "service 2"
    assert dao_fetch_all_services_by_user(user.id)[2].name == "service 3"


def test_get_services_by_partial_name(notify_db_session):
    create_service(service_name="Tadfield Police")
    create_service(service_name="Tadfield Air Base")
    create_service(service_name="London M25 Management Body")
    services_from_db = get_services_by_partial_name("Tadfield")
    assert len(services_from_db) == 2
    assert sorted([service.name for service in services_from_db]) == ["Tadfield Air Base", "Tadfield Police"]


def test_get_services_by_partial_name_is_case_insensitive(notify_db_session):
    create_service(service_name="Tadfield Police")
    services_from_db = get_services_by_partial_name("tadfield")
    assert services_from_db[0].name == "Tadfield Police"


def test_get_all_user_services_only_returns_services_user_has_access_to(notify_db_session):
    user = create_user()
    create_service(service_name="service 1", user=user, email_from="service.1")
    create_service(service_name="service 2", user=user, email_from="service.2")
    service_3 = create_service(service_name="service 3", user=user, email_from="service.3")
    new_user = User(
        name="Test User",
        email_address="new_user@digital.cabinet-office.gov.uk",
        password="password",
        mobile_number="+447700900986",
    )
    save_model_user(new_user, validated_email_access=True)
    dao_add_user_to_service(service_3, new_user)
    assert len(dao_fetch_all_services_by_user(user.id)) == 3
    assert dao_fetch_all_services_by_user(user.id)[0].name == "service 1"
    assert dao_fetch_all_services_by_user(user.id)[1].name == "service 2"
    assert dao_fetch_all_services_by_user(user.id)[2].name == "service 3"
    assert len(dao_fetch_all_services_by_user(new_user.id)) == 1
    assert dao_fetch_all_services_by_user(new_user.id)[0].name == "service 3"


def test_get_all_user_services_should_return_empty_list_if_no_services_for_user(notify_db_session):
    user = create_user()
    assert len(dao_fetch_all_services_by_user(user.id)) == 0


@freeze_time("2019-04-23T10:00:00")
def test_dao_fetch_live_services_data(sample_user):
    org = create_organisation(organisation_type="central")
    service = create_service(go_live_user=sample_user, go_live_at="2014-04-20T10:00:00")
    sms_template = create_template(service=service)
    service_2 = create_service(service_name="second", go_live_at="2017-04-20T10:00:00", go_live_user=sample_user)
    service_3 = create_service(service_name="third", go_live_at="2016-04-20T10:00:00")
    # below services should be filtered out:
    create_service(service_name="restricted", restricted=True)
    create_service(service_name="not_active", active=False)
    create_service(service_name="not_live", count_as_live=False)
    email_template = create_template(service=service, template_type="email")
    template_letter_1 = create_template(service=service, template_type="letter")
    template_letter_2 = create_template(service=service_2, template_type="letter")
    dao_add_service_to_organisation(service=service, organisation_id=org.id)
    # two sms billing records for 1st service within current financial year:
    create_ft_billing(bst_date="2019-04-20", template=sms_template)
    create_ft_billing(bst_date="2019-04-21", template=sms_template)
    # one sms billing record for 1st service from previous financial year, should not appear in the result:
    create_ft_billing(bst_date="2018-04-20", template=sms_template)
    # one email billing record for 1st service within current financial year:
    create_ft_billing(bst_date="2019-04-20", template=email_template)
    # one letter billing record for 1st service within current financial year:
    create_ft_billing(bst_date="2019-04-15", template=template_letter_1)
    # one letter billing record for 2nd service within current financial year:
    create_ft_billing(bst_date="2019-04-16", template=template_letter_2)

    # 1st service: billing from 2018 and 2019
    create_annual_billing(service.id, 500, 2018)
    create_annual_billing(service.id, 100, 2019)
    # 2nd service: billing from 2018
    create_annual_billing(service_2.id, 300, 2018)
    # 3rd service: billing from 2019
    create_annual_billing(service_3.id, 200, 2019)

    results = dao_fetch_live_services_data()
    assert len(results) == 3
    # checks the results and that they are ordered by date:
    assert results == [
        {
            "service_id": mock.ANY,
            "service_name": "Sample service",
            "organisation_name": "test_org_1",
            "organisation_type": "central",
            "consent_to_research": None,
            "contact_name": "Test User",
            "contact_email": "notify@digital.cabinet-office.gov.uk",
            "contact_mobile": "+447700900986",
            "live_date": datetime(2014, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "email_volume_intent": None,
            "letter_volume_intent": None,
            "sms_totals": 2,
            "email_totals": 1,
            "letter_totals": 1,
            "free_sms_fragment_limit": 100,
        },
        {
            "service_id": mock.ANY,
            "service_name": "third",
            "organisation_name": None,
            "consent_to_research": None,
            "organisation_type": None,
            "contact_name": None,
            "contact_email": None,
            "contact_mobile": None,
            "live_date": datetime(2016, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "email_volume_intent": None,
            "letter_volume_intent": None,
            "sms_totals": 0,
            "email_totals": 0,
            "letter_totals": 0,
            "free_sms_fragment_limit": 200,
        },
        {
            "service_id": mock.ANY,
            "service_name": "second",
            "organisation_name": None,
            "consent_to_research": None,
            "contact_name": "Test User",
            "contact_email": "notify@digital.cabinet-office.gov.uk",
            "contact_mobile": "+447700900986",
            "live_date": datetime(2017, 4, 20, 10, 0),
            "sms_volume_intent": None,
            "organisation_type": None,
            "email_volume_intent": None,
            "letter_volume_intent": None,
            "sms_totals": 0,
            "email_totals": 0,
            "letter_totals": 1,
            "free_sms_fragment_limit": 300,
        },
    ]


def test_get_service_by_id_returns_none_if_no_service(notify_db_session):
    with pytest.raises(NoResultFound) as e:
        dao_fetch_service_by_id(str(uuid.uuid4()))
    assert "No row was found when one was required" in str(e.value)


def test_get_service_by_id_returns_service(notify_db_session):
    service = create_service(service_name="testing", email_from="testing")
    assert dao_fetch_service_by_id(service.id).name == "testing"


def test_create_service_returns_service_with_default_permissions(notify_db_session):
    service = create_service(service_name="testing", email_from="testing", service_permissions=None)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(
        service.permissions,
        (
            BROADCAST_TYPE,
            SMS_TYPE,
            EMAIL_TYPE,
            LETTER_TYPE,
            INTERNATIONAL_SMS_TYPE,
            UPLOAD_LETTERS,
            INTERNATIONAL_LETTERS,
        ),
    )


@pytest.mark.parametrize(
    "permission_to_remove, permissions_remaining",
    [
        (
            SMS_TYPE,
            (EMAIL_TYPE, BROADCAST_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS),
        ),
        (
            EMAIL_TYPE,
            (SMS_TYPE, BROADCAST_TYPE, LETTER_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS),
        ),
    ],
)
def test_remove_permission_from_service_by_id_returns_service_with_correct_permissions(
    notify_db_session, permission_to_remove, permissions_remaining
):
    service = create_service(service_permissions=None)
    dao_remove_service_permission(service_id=service.id, permission=permission_to_remove)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(service.permissions, permissions_remaining)


def test_removing_all_permission_returns_service_with_no_permissions(notify_db_session):
    service = create_service()
    dao_remove_service_permission(service_id=service.id, permission=BROADCAST_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=SMS_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=EMAIL_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=INTERNATIONAL_SMS_TYPE)
    dao_remove_service_permission(service_id=service.id, permission=UPLOAD_LETTERS)
    dao_remove_service_permission(service_id=service.id, permission=INTERNATIONAL_LETTERS)

    service = dao_fetch_service_by_id(service.id)
    assert len(service.permissions) == 0


def test_create_service_by_id_adding_and_removing_letter_returns_service_without_letter(service_factory):
    service = service_factory.get("testing", email_from="testing")

    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    dao_add_service_permission(service_id=service.id, permission=LETTER_TYPE)

    service = dao_fetch_service_by_id(service.id)
    _assert_service_permissions(
        service.permissions,
        (
            BROADCAST_TYPE,
            SMS_TYPE,
            EMAIL_TYPE,
            LETTER_TYPE,
            INTERNATIONAL_SMS_TYPE,
            UPLOAD_LETTERS,
            INTERNATIONAL_LETTERS,
        ),
    )

    dao_remove_service_permission(service_id=service.id, permission=LETTER_TYPE)
    service = dao_fetch_service_by_id(service.id)

    _assert_service_permissions(
        service.permissions,
        (BROADCAST_TYPE, SMS_TYPE, EMAIL_TYPE, INTERNATIONAL_SMS_TYPE, UPLOAD_LETTERS, INTERNATIONAL_LETTERS),
    )


def test_create_service_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(
        name="service_name", email_from="email_from", message_limit=1000, restricted=False, created_by=user
    )
    dao_create_service(service, user)
    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 1

    service_from_db = Service.query.first()
    service_history = Service.get_history_model().query.first()

    assert service_from_db.id == service_history.id
    assert service_from_db.name == service_history.name
    assert service_from_db.version == 1
    assert service_from_db.version == service_history.version
    assert user.id == service_history.created_by_id
    assert service_from_db.created_by.id == service_history.created_by_id


def test_update_service_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(
        name="service_name", email_from="email_from", message_limit=1000, restricted=False, created_by=user
    )
    dao_create_service(service, user)

    assert Service.query.count() == 1
    assert Service.query.first().version == 1
    assert Service.get_history_model().query.count() == 1

    service.name = "updated_service_name"
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 2

    service_from_db = Service.query.first()

    assert service_from_db.version == 2

    assert Service.get_history_model().query.filter_by(name="service_name").one().version == 1
    assert Service.get_history_model().query.filter_by(name="updated_service_name").one().version == 2


def test_update_service_permission_creates_a_history_record_with_current_data(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(
        name="service_name", email_from="email_from", message_limit=1000, restricted=False, created_by=user
    )
    dao_create_service(
        service,
        user,
        service_permissions=[
            SMS_TYPE,
            EMAIL_TYPE,
            INTERNATIONAL_SMS_TYPE,
        ],
    )

    service.permissions.append(ServicePermission(service_id=service.id, permission="letter"))
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 2

    service_from_db = Service.query.first()

    assert service_from_db.version == 2

    _assert_service_permissions(
        service.permissions,
        (
            SMS_TYPE,
            EMAIL_TYPE,
            INTERNATIONAL_SMS_TYPE,
            LETTER_TYPE,
        ),
    )

    permission = [p for p in service.permissions if p.permission == "sms"][0]
    service.permissions.remove(permission)
    dao_update_service(service)

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 3

    service_from_db = Service.query.first()
    assert service_from_db.version == 3
    _assert_service_permissions(
        service.permissions,
        (
            EMAIL_TYPE,
            INTERNATIONAL_SMS_TYPE,
            LETTER_TYPE,
        ),
    )

    history = Service.get_history_model().query.filter_by(name="service_name").order_by("version").all()

    assert len(history) == 3
    assert history[2].version == 3


def test_create_service_and_history_is_transactional(notify_db_session):
    user = create_user()
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    service = Service(name=None, email_from="email_from", message_limit=1000, restricted=False, created_by=user)

    with pytest.raises(IntegrityError) as excinfo:
        dao_create_service(service, user)

    assert 'column "name" of relation "services_history" violates not-null constraint' in str(excinfo.value)
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0


def test_delete_service_and_associated_objects(notify_db_session):
    user = create_user()
    organisation = create_organisation()
    service = create_service(user=user, service_permissions=None, organisation=organisation)
    create_user_code(user=user, code="somecode", code_type="email")
    create_user_code(user=user, code="somecode", code_type="sms")
    create_invited_user(service=service)
    user.organisations = [organisation]

    assert ServicePermission.query.count() == len(
        (
            BROADCAST_TYPE,
            SMS_TYPE,
            EMAIL_TYPE,
            LETTER_TYPE,
            INTERNATIONAL_SMS_TYPE,
            UPLOAD_LETTERS,
            INTERNATIONAL_LETTERS,
        )
    )

    delete_service_and_all_associated_db_objects(service)
    assert VerifyCode.query.count() == 0
    assert ApiKey.query.count() == 0
    assert ApiKey.get_history_model().query.count() == 0
    assert Template.query.count() == 0
    assert TemplateHistory.query.count() == 0
    assert Permission.query.count() == 0
    assert User.query.count() == 1  # service creator is not deleted
    assert InvitedUser.query.count() == 0
    assert Service.query.count() == 0
    assert Service.get_history_model().query.count() == 0
    assert ServicePermission.query.count() == 0
    # the organisation hasn't been deleted
    assert Organisation.query.count() == 1


def test_add_existing_user_to_another_service_doesnot_change_old_permissions(notify_db_session):
    user = create_user()

    service_one = Service(
        name="service_one", email_from="service_one", message_limit=1000, restricted=False, created_by=user
    )

    dao_create_service(service_one, user)
    assert user.id == service_one.users[0].id
    test_user_permissions = Permission.query.filter_by(service=service_one, user=user).all()
    assert len(test_user_permissions) == 8

    other_user = User(
        name="Other Test User",
        email_address="other_user@digital.cabinet-office.gov.uk",
        password="password",
        mobile_number="+447700900987",
    )
    save_model_user(other_user, validated_email_access=True)
    service_two = Service(
        name="service_two", email_from="service_two", message_limit=1000, restricted=False, created_by=other_user
    )
    dao_create_service(service_two, other_user)

    assert other_user.id == service_two.users[0].id
    other_user_permissions = Permission.query.filter_by(service=service_two, user=other_user).all()
    assert len(other_user_permissions) == 8

    other_user_service_one_permissions = Permission.query.filter_by(service=service_one, user=other_user).all()
    assert len(other_user_service_one_permissions) == 0

    # adding the other_user to service_one should leave all other_user permissions on service_two intact
    permissions = []
    for p in ["send_emails", "send_texts", "send_letters"]:
        permissions.append(Permission(permission=p))

    dao_add_user_to_service(service_one, other_user, permissions=permissions)

    other_user_service_one_permissions = Permission.query.filter_by(service=service_one, user=other_user).all()
    assert len(other_user_service_one_permissions) == 3

    other_user_service_two_permissions = Permission.query.filter_by(service=service_two, user=other_user).all()
    assert len(other_user_service_two_permissions) == 8


def test_dao_fetch_active_users_for_service_returns_active_only(notify_db_session):
    active_user = create_user(email="active@foo.com", state="active")
    pending_user = create_user(email="pending@foo.com", state="pending")
    service = create_service(user=active_user)
    dao_add_user_to_service(service, pending_user)
    users = dao_fetch_active_users_for_service(service.id)

    assert len(users) == 1


def _assert_service_permissions(service_permissions, expected):
    assert len(service_permissions) == len(expected)
    assert set(expected) == set(p.permission for p in service_permissions)


def create_email_sms_letter_template():
    service = create_service()
    template_one = create_template(service=service, template_name="1", template_type="email")
    template_two = create_template(service=service, template_name="2", template_type="sms")
    template_three = create_template(service=service, template_name="3", template_type="letter")
    return template_one, template_three, template_two


def test_get_live_services_with_organisation(sample_organisation):
    trial_service = create_service(service_name="trial service", restricted=True)
    live_service = create_service(service_name="count as live")
    live_service_diff_org = create_service(service_name="live service different org")
    dont_count_as_live = create_service(service_name="dont count as live", count_as_live=False)
    inactive_service = create_service(service_name="inactive", active=False)
    service_without_org = create_service(service_name="no org")
    another_org = create_organisation(
        name="different org",
    )

    dao_add_service_to_organisation(trial_service, sample_organisation.id)
    dao_add_service_to_organisation(live_service, sample_organisation.id)
    dao_add_service_to_organisation(dont_count_as_live, sample_organisation.id)
    dao_add_service_to_organisation(inactive_service, sample_organisation.id)
    dao_add_service_to_organisation(live_service_diff_org, another_org.id)

    services = get_live_services_with_organisation()
    assert len(services) == 3
    assert ([(x.service_name, x.organisation_name) for x in services]) == [
        (live_service_diff_org.name, another_org.name),
        (live_service.name, sample_organisation.name),
        (service_without_org.name, None),
    ]
