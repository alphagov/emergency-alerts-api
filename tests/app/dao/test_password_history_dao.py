from datetime import datetime, timedelta

import pytest

from app.dao.password_history_dao import (
    dao_create_password_for_user_id,
    dao_get_all_passwords_for_user,
    dao_get_count_of_all_historic_passwords_for_user

)
from tests.app.conftest import fake_uuid


def test_get_password_history_returns_all_past_passwords(notify_db_session):
    """
    Creates 3 failed login records and checks that 3 are returned in dao_get_count_of_all_failed_logins_for_ip.
    """
    dao_create_password_for_user_id(fake_uuid, "test")
    dao_create_password_for_user_id(fake_uuid, "test")
    dao_create_password_for_user_id(fake_uuid, "test")
    response = dao_get_all_passwords_for_user(fake_uuid)
    assert len(response) == 3


def test_get_password_history_count_returns_count_of_past_passwords(notify_db_session):
    """
    Creates 3 failed login records and checks that 3 are returned in dao_get_count_of_all_failed_logins_for_ip.
    """
    dao_create_password_for_user_id(fake_uuid, "test")
    dao_create_password_for_user_id(fake_uuid, "test")
    dao_create_password_for_user_id(fake_uuid, "test")
    response = dao_get_count_of_all_historic_passwords_for_user(fake_uuid)
    assert response == 3


def test_create_password_adds_password_to_password_history(notify_db_session):
    """
    Creates 3 failed login records and checks that 3 are returned in dao_get_count_of_all_failed_logins_for_ip.
    """
    dao_create_password_for_user_id(fake_uuid, "test")
    assert dao_get_all_passwords_for_user[0] == ""