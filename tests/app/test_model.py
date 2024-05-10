import pytest
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError

from app.models import (
    EMAIL_TYPE,
    MOBILE_TYPE,
    NOTIFICATION_CREATED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_FAILED,
    NOTIFICATION_PENDING,
    NOTIFICATION_SENDING,
    NOTIFICATION_STATUS_LETTER_ACCEPTED,
    NOTIFICATION_STATUS_LETTER_RECEIVED,
    NOTIFICATION_STATUS_TYPES_FAILED,
    NOTIFICATION_TECHNICAL_FAILURE,
    PRECOMPILED_TEMPLATE_NAME,
    SMS_TYPE,
    Notification,
    ServiceGuestList,
)
from tests.app.db import (
    create_letter_contact,
    create_notification,
    create_reply_to_email,
    create_template,
    create_template_folder,
)


@pytest.mark.parametrize("mobile_number", ["07700 900678", "+44 7700 900678"])
def test_should_build_service_guest_list_from_mobile_number(mobile_number):
    service_guest_list = ServiceGuestList.from_string("service_id", MOBILE_TYPE, mobile_number)

    assert service_guest_list.recipient == mobile_number


@pytest.mark.parametrize("email_address", ["test@example.com"])
def test_should_build_service_guest_list_from_email_address(email_address):
    service_guest_list = ServiceGuestList.from_string("service_id", EMAIL_TYPE, email_address)

    assert service_guest_list.recipient == email_address


@pytest.mark.parametrize(
    "contact, recipient_type", [("", None), ("07700dsadsad", MOBILE_TYPE), ("gmail.com", EMAIL_TYPE)]
)
def test_should_not_build_service_guest_list_from_invalid_contact(recipient_type, contact):
    with pytest.raises(ValueError):
        ServiceGuestList.from_string("service_id", recipient_type, contact)


@pytest.mark.parametrize(
    "initial_statuses, expected_statuses",
    [
        # passing in single statuses as strings
        (NOTIFICATION_FAILED, NOTIFICATION_STATUS_TYPES_FAILED),
        (NOTIFICATION_STATUS_LETTER_ACCEPTED, [NOTIFICATION_SENDING, NOTIFICATION_CREATED]),
        (NOTIFICATION_CREATED, [NOTIFICATION_CREATED]),
        (NOTIFICATION_TECHNICAL_FAILURE, [NOTIFICATION_TECHNICAL_FAILURE]),
        # passing in lists containing single statuses
        ([NOTIFICATION_FAILED], NOTIFICATION_STATUS_TYPES_FAILED),
        ([NOTIFICATION_CREATED], [NOTIFICATION_CREATED]),
        ([NOTIFICATION_TECHNICAL_FAILURE], [NOTIFICATION_TECHNICAL_FAILURE]),
        (NOTIFICATION_STATUS_LETTER_RECEIVED, NOTIFICATION_DELIVERED),
        # passing in lists containing multiple statuses
        ([NOTIFICATION_FAILED, NOTIFICATION_CREATED], NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_CREATED]),
        ([NOTIFICATION_CREATED, NOTIFICATION_PENDING], [NOTIFICATION_CREATED, NOTIFICATION_PENDING]),
        (
            [NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE],
            [NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE],
        ),
        (
            [NOTIFICATION_FAILED, NOTIFICATION_STATUS_LETTER_ACCEPTED],
            NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_SENDING, NOTIFICATION_CREATED],
        ),
        # checking we don't end up with duplicates
        (
            [NOTIFICATION_FAILED, NOTIFICATION_CREATED, NOTIFICATION_TECHNICAL_FAILURE],
            NOTIFICATION_STATUS_TYPES_FAILED + [NOTIFICATION_CREATED],
        ),
    ],
)
def test_status_conversion(initial_statuses, expected_statuses):
    converted_statuses = Notification.substitute_status(initial_statuses)
    assert len(converted_statuses) == len(expected_statuses)
    assert set(converted_statuses) == set(expected_statuses)


@freeze_time("2016-01-01 11:09:00.000000")
@pytest.mark.parametrize(
    "template_type, recipient",
    [
        ("sms", "+447700900855"),
        ("email", "foo@bar.com"),
    ],
)
def test_notification_for_csv_returns_correct_type(sample_service, template_type, recipient):
    template = create_template(sample_service, template_type=template_type)
    notification = create_notification(template, to_field=recipient)

    serialized = notification.serialize_for_csv()
    assert serialized["template_type"] == template_type


@freeze_time("2016-01-01 11:09:00.000000")
def test_notification_for_csv_returns_correct_job_row_number(sample_job):
    notification = create_notification(sample_job.template, sample_job, job_row_number=0)

    serialized = notification.serialize_for_csv()
    assert serialized["row_number"] == 1


def test_notification_personalisation_getter_returns_empty_dict_from_None():
    noti = Notification()
    noti._personalisation = None
    assert noti.personalisation == {}


def test_notification_subject_is_none_for_sms(sample_service):
    template = create_template(service=sample_service, template_type=SMS_TYPE)
    notification = create_notification(template=template)
    assert notification.subject is None


def test_email_notification_serializes_with_subject(client, sample_email_template):
    res = sample_email_template.serialize_for_v2()
    assert res["subject"] == "Email Subject"


def test_notification_requires_a_valid_template_version(client, sample_template):
    sample_template.version = 2
    with pytest.raises(IntegrityError):
        create_notification(sample_template)


def test_service_get_default_reply_to_email_address(sample_service):
    create_reply_to_email(service=sample_service, email_address="default@email.com")

    assert sample_service.get_default_reply_to_email_address() == "default@email.com"


def test_service_get_default_contact_letter(sample_service):
    create_letter_contact(service=sample_service, contact_block="London,\nNW1A 1AA")

    assert sample_service.get_default_letter_contact() == "London,\nNW1A 1AA"


def test_is_precompiled_letter_false(sample_letter_template):
    assert not sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_true(sample_letter_template):
    sample_letter_template.hidden = True
    sample_letter_template.name = PRECOMPILED_TEMPLATE_NAME
    assert sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_hidden_true_not_name(sample_letter_template):
    sample_letter_template.hidden = True
    assert not sample_letter_template.is_precompiled_letter


def test_is_precompiled_letter_name_correct_not_hidden(sample_letter_template):
    sample_letter_template.name = PRECOMPILED_TEMPLATE_NAME
    assert not sample_letter_template.is_precompiled_letter


def test_template_folder_is_parent(sample_service):
    x = None
    folders = []
    for i in range(5):
        x = create_template_folder(sample_service, name=str(i), parent=x)
        folders.append(x)

    assert folders[0].is_parent_of(folders[1])
    assert folders[0].is_parent_of(folders[2])
    assert folders[0].is_parent_of(folders[4])
    assert folders[1].is_parent_of(folders[2])
    assert not folders[1].is_parent_of(folders[0])


@pytest.mark.parametrize("is_platform_admin", (False, True))
def test_user_can_use_webauthn_if_platform_admin(sample_user, is_platform_admin):
    sample_user.platform_admin = is_platform_admin
    assert sample_user.can_use_webauthn == is_platform_admin


@pytest.mark.parametrize(
    ("auth_type", "can_use_webauthn"), [("email_auth", False), ("sms_auth", False), ("webauthn_auth", True)]
)
def test_user_can_use_webauthn_if_they_login_with_it(sample_user, auth_type, can_use_webauthn):
    sample_user.auth_type = auth_type
    assert sample_user.can_use_webauthn == can_use_webauthn


def test_user_can_use_webauthn_if_in_broadcast_org(sample_broadcast_service):
    assert sample_broadcast_service.users[0].can_use_webauthn


def test_user_can_use_webauthn_if_in_notify_team(notify_service):
    assert notify_service.users[0].can_use_webauthn
