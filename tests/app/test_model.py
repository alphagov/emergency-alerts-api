from datetime import date, datetime

import pytest

from app.models import ApiKey
from tests.app.db import create_template_folder


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


@pytest.mark.parametrize("is_platform_admin_capable", (False, True))
def test_user_can_use_webauthn_if_platform_admin(sample_user, is_platform_admin_capable):
    sample_user.platform_admin_capable = is_platform_admin_capable
    assert sample_user.can_use_webauthn == is_platform_admin_capable


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


@pytest.mark.parametrize(
    "created_at, expected_scheduled_expiry_date",
    [
        (datetime(2026, 11, 26, 0, 0, 1), date(2027, 11, 26)),
        (datetime(2026, 11, 26, 23, 59, 59), date(2027, 11, 26)),
        # No 29 February the following year, so it falls back to the end of the month
        (datetime(2028, 2, 29, 12, 0), date(2029, 2, 28)),
    ],
)
def test_api_key_scheduled_expiry_date_is_12_months_after_creation(created_at, expected_scheduled_expiry_date):
    assert ApiKey(created_at=created_at).scheduled_expiry_date == expected_scheduled_expiry_date


def test_api_key_scheduled_expiry_date_is_none_before_key_is_saved():
    assert ApiKey().scheduled_expiry_date is None
