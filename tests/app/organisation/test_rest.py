import uuid

import pytest
from freezegun import freeze_time
from sqlalchemy.exc import SQLAlchemyError

from app.dao.organisation_dao import (
    dao_add_service_to_organisation,
    dao_add_user_to_organisation,
)
from app.models import (
    INVITE_ACCEPTED,
    INVITE_CANCELLED,
    AnnualBilling,
    Organisation,
)
from tests.app.db import (
    create_domain,
    create_organisation,
    create_service,
    create_user,
)


def test_get_all_organisations(admin_request, notify_db_session):
    create_organisation(name="inactive org", active=False, organisation_type="central")
    create_organisation(name="active org", domains=["example.com"])

    response = admin_request.get("organisation.get_organisations", _expected_status=200)

    assert len(response) == 2
    assert (
        set(response[0].keys())
        == set(response[1].keys())
        == {
            "name",
            "id",
            "active",
            "count_of_live_services",
            "domains",
            "organisation_type",
        }
    )
    assert response[0]["name"] == "active org"
    assert response[0]["active"] is True
    assert response[0]["count_of_live_services"] == 0
    assert response[0]["domains"] == ["example.com"]
    assert response[0]["organisation_type"] is None
    assert response[1]["name"] == "inactive org"
    assert response[1]["active"] is False
    assert response[1]["count_of_live_services"] == 0
    assert response[1]["domains"] == []
    assert response[1]["organisation_type"] == "central"


def test_get_organisation_by_id(admin_request, notify_db_session):
    org = create_organisation()

    response = admin_request.get("organisation.get_organisation_by_id", _expected_status=200, organisation_id=org.id)

    assert set(response.keys()) == {
        "id",
        "name",
        "active",
        "crown",
        "organisation_type",
        "agreement_signed",
        "agreement_signed_at",
        "agreement_signed_by_id",
        "agreement_signed_version",
        "agreement_signed_on_behalf_of_name",
        "agreement_signed_on_behalf_of_email_address",
        "domains",
        "request_to_go_live_notes",
        "count_of_live_services",
        "notes",
        "billing_contact_names",
        "billing_contact_email_addresses",
        "billing_reference",
        "purchase_order_number",
    }
    assert response["id"] == str(org.id)
    assert response["name"] == "test_org_1"
    assert response["active"] is True
    assert response["crown"] is None
    assert response["organisation_type"] is None
    assert response["agreement_signed"] is None
    assert response["agreement_signed_by_id"] is None
    assert response["agreement_signed_version"] is None
    assert response["domains"] == []
    assert response["request_to_go_live_notes"] is None
    assert response["count_of_live_services"] == 0
    assert response["agreement_signed_on_behalf_of_name"] is None
    assert response["agreement_signed_on_behalf_of_email_address"] is None
    assert response["notes"] is None
    assert response["billing_contact_names"] is None
    assert response["billing_contact_email_addresses"] is None
    assert response["billing_reference"] is None
    assert response["purchase_order_number"] is None


def test_get_organisation_by_id_returns_domains(admin_request, notify_db_session):
    org = create_organisation(
        domains=[
            "foo.gov.uk",
            "bar.gov.uk",
        ]
    )

    response = admin_request.get("organisation.get_organisation_by_id", _expected_status=200, organisation_id=org.id)

    assert set(response["domains"]) == {
        "foo.gov.uk",
        "bar.gov.uk",
    }


@pytest.mark.parametrize(
    "domain, expected_status",
    (
        ("foo.gov.uk", 200),
        ("bar.gov.uk", 200),
        ("oof.gov.uk", 404),
        pytest.param(
            "rab.gov.uk",
            200,
            marks=pytest.mark.xfail(raises=AssertionError),
        ),
        (None, 400),
        ("personally.identifying.information@example.com", 400),
    ),
)
def test_get_organisation_by_domain(admin_request, notify_db_session, domain, expected_status):
    org = create_organisation()
    other_org = create_organisation("Other organisation")
    create_domain("foo.gov.uk", org.id)
    create_domain("bar.gov.uk", org.id)
    create_domain("rab.gov.uk", other_org.id)

    response = admin_request.get(
        "organisation.get_organisation_by_domain",
        _expected_status=expected_status,
        domain=domain,
    )

    if expected_status == 200:
        assert response["id"] == str(org.id)
    else:
        assert response["result"] == "error"


@pytest.mark.parametrize("crown", [True, False])
def test_post_create_organisation(admin_request, notify_db_session, crown):
    data = {
        "name": "test organisation",
        "active": True,
        "crown": crown,
        "organisation_type": "local",
    }

    response = admin_request.post("organisation.create_organisation", _data=data, _expected_status=201)

    organisations = Organisation.query.all()

    assert data["name"] == response["name"]
    assert data["active"] == response["active"]
    assert data["crown"] == response["crown"]
    assert data["organisation_type"] == response["organisation_type"]

    assert len(organisations) == 1


def test_post_create_organisation_existing_name_raises_400(admin_request, sample_organisation):
    data = {
        "name": sample_organisation.name,
        "active": True,
        "crown": True,
        "organisation_type": "central",
    }

    response = admin_request.post("organisation.create_organisation", _data=data, _expected_status=400)

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert response["message"] == "Organisation name already exists"


@pytest.mark.parametrize(
    "data, expected_error",
    (
        (
            {
                "active": False,
                "crown": True,
                "organisation_type": "central",
            },
            "name is a required property",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "organisation_type": "central",
            },
            "crown is a required property",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "crown": True,
            },
            "organisation_type is a required property",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "crown": None,
                "organisation_type": "central",
            },
            "crown None is not of type boolean",
        ),
        (
            {
                "active": False,
                "name": "Service name",
                "crown": False,
                "organisation_type": "foo",
            },
            (
                "organisation_type foo is not one of "
                "[central, local, nhs_central, nhs_local, nhs_gp, emergency_service, school_or_college, other]"
            ),
        ),
    ),
)
def test_post_create_organisation_with_missing_data_gives_validation_error(
    admin_request,
    notify_db_session,
    data,
    expected_error,
):
    response = admin_request.post("organisation.create_organisation", _data=data, _expected_status=400)

    assert len(response["errors"]) == 1
    assert response["errors"][0]["error"] == "ValidationError"
    assert response["errors"][0]["message"] == expected_error


@pytest.mark.parametrize("crown", (None, True, False))
def test_post_update_organisation_updates_fields(
    admin_request,
    notify_db_session,
    crown,
):
    org = create_organisation()
    data = {
        "name": "new organisation name",
        "active": False,
        "crown": crown,
        "organisation_type": "central",
    }
    assert org.crown is None

    admin_request.post("organisation.update_organisation", _data=data, organisation_id=org.id, _expected_status=204)

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert organisation[0].id == org.id
    assert organisation[0].name == data["name"]
    assert organisation[0].active == data["active"]
    assert organisation[0].crown == crown
    assert organisation[0].domains == []
    assert organisation[0].organisation_type == "central"


@pytest.mark.parametrize(
    "domain_list",
    (
        ["example.com"],
        ["example.com", "example.org", "example.net"],
        [],
    ),
)
def test_post_update_organisation_updates_domains(
    admin_request,
    notify_db_session,
    domain_list,
):
    org = create_organisation(name="test_org_2")
    data = {
        "domains": domain_list,
    }

    admin_request.post("organisation.update_organisation", _data=data, organisation_id=org.id, _expected_status=204)

    organisation = Organisation.query.all()

    assert len(organisation) == 1
    assert [domain.domain for domain in organisation[0].domains] == domain_list


def test_update_other_organisation_attributes_doesnt_clear_domains(
    admin_request,
    notify_db_session,
):
    org = create_organisation(name="test_org_2")
    create_domain("example.gov.uk", org.id)

    admin_request.post(
        "organisation.update_organisation",
        _data={
            "crown": True,
        },
        organisation_id=org.id,
        _expected_status=204,
    )

    assert [domain.domain for domain in org.domains] == ["example.gov.uk"]


def test_post_update_organisation_raises_400_on_existing_org_name(admin_request, sample_organisation):
    org = create_organisation()
    data = {"name": sample_organisation.name, "active": False}

    response = admin_request.post(
        "organisation.update_organisation", _data=data, organisation_id=org.id, _expected_status=400
    )

    assert response["message"] == "Organisation name already exists"


def test_post_update_organisation_gives_404_status_if_org_does_not_exist(admin_request, notify_db_session):
    data = {"name": "new organisation name"}

    admin_request.post(
        "organisation.update_organisation",
        _data=data,
        organisation_id="31d42ce6-3dac-45a7-95cb-94423d5ca03c",
        _expected_status=404,
    )

    organisation = Organisation.query.all()

    assert not organisation


def test_post_update_organisation_returns_400_if_domain_is_duplicate(admin_request, notify_db_session):
    org = create_organisation()
    org2 = create_organisation(name="Second org")
    create_domain("same.com", org.id)

    data = {"domains": ["new.com", "same.com"]}

    response = admin_request.post(
        "organisation.update_organisation", _data=data, organisation_id=org2.id, _expected_status=400
    )

    assert response["message"] == "Domain already exists"


@pytest.mark.parametrize("invited_user_status", [INVITE_CANCELLED, INVITE_ACCEPTED])
def test_archive_organisation_sets_active_to_false(
    admin_request,
    sample_organisation,
    sample_invited_org_user,
    invited_user_status,
):
    # Invited users with 'cancelled' or 'accepted' don't stop orgs from being archived
    sample_invited_org_user.status = invited_user_status

    assert sample_organisation.active

    admin_request.post(
        "organisation.archive_organisation", organisation_id=sample_organisation.id, _expected_status=204
    )

    assert not sample_organisation.active


def test_archive_organisation_raises_an_error_if_org_has_team_members(
    admin_request,
    sample_organisation,
    sample_user,
):
    dao_add_user_to_organisation(sample_organisation.id, sample_user.id)

    response = admin_request.post(
        "organisation.archive_organisation", organisation_id=sample_organisation.id, _expected_status=400
    )
    assert response["message"] == "Cannot archive an organisation with team members or invited team members"

    assert sample_organisation.active


def test_archive_organisation_raises_an_error_if_org_has_pending_invited_team_members(
    admin_request,
    sample_organisation,
    sample_invited_org_user,
):
    response = admin_request.post(
        "organisation.archive_organisation", organisation_id=sample_organisation.id, _expected_status=400
    )
    assert response["message"] == "Cannot archive an organisation with team members or invited team members"

    assert sample_organisation.active


@pytest.mark.parametrize(
    "service_active, service_trial_mode",
    [
        (True, True),
        (False, True),
        (False, False),
        (True, False),
    ],
)
def test_archive_organisation_raises_an_error_if_org_has_services(
    admin_request,
    sample_organisation,
    sample_service,
    service_active,
    service_trial_mode,
):
    sample_service.active = service_active
    sample_service.restricted = service_trial_mode
    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    response = admin_request.post(
        "organisation.archive_organisation", organisation_id=sample_organisation.id, _expected_status=400
    )
    assert response["message"] == "Cannot archive an organisation with services"

    assert sample_organisation.active


def test_post_link_service_to_organisation(admin_request, sample_service):
    data = {"service_id": str(sample_service.id)}
    organisation = create_organisation(organisation_type="central")

    admin_request.post(
        "organisation.link_service_to_organisation", _data=data, organisation_id=organisation.id, _expected_status=204
    )
    assert len(organisation.services) == 1
    assert sample_service.organisation_type == "central"


@freeze_time("2021-09-24 13:30")
def test_post_link_service_to_organisation_inserts_annual_billing(admin_request, sample_service):
    data = {"service_id": str(sample_service.id)}
    organisation = create_organisation(organisation_type="central")
    assert len(organisation.services) == 0
    assert len(AnnualBilling.query.all()) == 0
    admin_request.post(
        "organisation.link_service_to_organisation", _data=data, organisation_id=organisation.id, _expected_status=204
    )

    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1
    assert annual_billing[0].free_sms_fragment_limit == 150000


def test_post_link_service_to_organisation_rollback_service_if_annual_billing_update_fails(
    admin_request, sample_service, mocker
):
    mocker.patch("app.dao.annual_billing_dao.dao_create_or_update_annual_billing_for_year", side_effect=SQLAlchemyError)
    data = {"service_id": str(sample_service.id)}
    assert not sample_service.organisation_type

    organisation = create_organisation(organisation_type="central")
    assert len(organisation.services) == 0
    assert len(AnnualBilling.query.all()) == 0
    with pytest.raises(expected_exception=SQLAlchemyError):
        admin_request.post("organisation.link_service_to_organisation", _data=data, organisation_id=organisation.id)
    assert not sample_service.organisation_type
    assert len(organisation.services) == 0
    assert len(AnnualBilling.query.all()) == 0


@freeze_time("2021-09-24 13:30")
def test_post_link_service_to_another_org(admin_request, sample_service, sample_organisation):
    data = {"service_id": str(sample_service.id)}
    assert len(sample_organisation.services) == 0
    assert not sample_service.organisation_type
    admin_request.post(
        "organisation.link_service_to_organisation",
        _data=data,
        organisation_id=sample_organisation.id,
        _expected_status=204,
    )

    assert len(sample_organisation.services) == 1
    assert not sample_service.organisation_type

    new_org = create_organisation(organisation_type="central")
    admin_request.post(
        "organisation.link_service_to_organisation", _data=data, organisation_id=new_org.id, _expected_status=204
    )
    assert not sample_organisation.services
    assert len(new_org.services) == 1
    assert sample_service.organisation_type == "central"
    annual_billing = AnnualBilling.query.all()
    assert len(annual_billing) == 1
    assert annual_billing[0].free_sms_fragment_limit == 150000


def test_post_link_service_to_organisation_nonexistent_organisation(admin_request, sample_service, fake_uuid):
    data = {"service_id": str(sample_service.id)}

    admin_request.post(
        "organisation.link_service_to_organisation", _data=data, organisation_id=fake_uuid, _expected_status=404
    )


def test_post_link_service_to_organisation_nonexistent_service(admin_request, sample_organisation, fake_uuid):
    data = {"service_id": fake_uuid}

    admin_request.post(
        "organisation.link_service_to_organisation",
        _data=data,
        organisation_id=str(sample_organisation.id),
        _expected_status=404,
    )


def test_post_link_service_to_organisation_missing_payload(admin_request, sample_organisation, fake_uuid):
    admin_request.post(
        "organisation.link_service_to_organisation", organisation_id=str(sample_organisation.id), _expected_status=400
    )


def test_rest_get_organisation_services(admin_request, sample_organisation, sample_service):
    dao_add_service_to_organisation(sample_service, sample_organisation.id)
    response = admin_request.get(
        "organisation.get_organisation_services", organisation_id=str(sample_organisation.id), _expected_status=200
    )

    assert response == [sample_service.serialize_for_org_dashboard()]


def test_rest_get_organisation_services_is_ordered_by_name(admin_request, sample_organisation, sample_service):
    service_2 = create_service(service_name="service 2")
    service_1 = create_service(service_name="service 1")
    dao_add_service_to_organisation(service_1, sample_organisation.id)
    dao_add_service_to_organisation(service_2, sample_organisation.id)
    dao_add_service_to_organisation(sample_service, sample_organisation.id)

    response = admin_request.get(
        "organisation.get_organisation_services", organisation_id=str(sample_organisation.id), _expected_status=200
    )

    assert response[0]["name"] == sample_service.name
    assert response[1]["name"] == service_1.name
    assert response[2]["name"] == service_2.name


def test_rest_get_organisation_services_inactive_services_at_end(admin_request, sample_organisation):
    inactive_service = create_service(service_name="inactive service", active=False)
    service = create_service()
    inactive_service_1 = create_service(service_name="inactive service 1", active=False)

    dao_add_service_to_organisation(inactive_service, sample_organisation.id)
    dao_add_service_to_organisation(service, sample_organisation.id)
    dao_add_service_to_organisation(inactive_service_1, sample_organisation.id)

    response = admin_request.get(
        "organisation.get_organisation_services", organisation_id=str(sample_organisation.id), _expected_status=200
    )

    assert response[0]["name"] == service.name
    assert response[1]["name"] == inactive_service.name
    assert response[2]["name"] == inactive_service_1.name


def test_add_user_to_organisation_returns_added_user(admin_request, sample_organisation, sample_user):
    response = admin_request.post(
        "organisation.add_user_to_organisation",
        organisation_id=str(sample_organisation.id),
        user_id=str(sample_user.id),
        _expected_status=200,
    )

    assert response["data"]["id"] == str(sample_user.id)
    assert len(response["data"]["organisations"]) == 1
    assert response["data"]["organisations"][0] == str(sample_organisation.id)


def test_add_user_to_organisation_returns_404_if_user_does_not_exist(admin_request, sample_organisation):
    admin_request.post(
        "organisation.add_user_to_organisation",
        organisation_id=str(sample_organisation.id),
        user_id=str(uuid.uuid4()),
        _expected_status=404,
    )


def test_remove_user_from_organisation(admin_request, sample_organisation, sample_user):
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=sample_user.id)

    admin_request.delete(
        "organisation.remove_user_from_organisation", organisation_id=sample_organisation.id, user_id=sample_user.id
    )

    assert sample_organisation.users == []


def test_remove_user_from_organisation_when_user_is_not_an_org_member(admin_request, sample_organisation, sample_user):
    resp = admin_request.delete(
        "organisation.remove_user_from_organisation",
        organisation_id=sample_organisation.id,
        user_id=sample_user.id,
        _expected_status=404,
    )

    assert resp == {"result": "error", "message": "User not found"}


def test_get_organisation_users_returns_users_for_organisation(admin_request, sample_organisation):
    first = create_user(email="first@invited.com")
    second = create_user(email="another@invited.com")
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=first.id)
    dao_add_user_to_organisation(organisation_id=sample_organisation.id, user_id=second.id)

    response = admin_request.get(
        "organisation.get_organisation_users", organisation_id=sample_organisation.id, _expected_status=200
    )

    assert len(response["data"]) == 2
    assert response["data"][0]["id"] == str(first.id)
