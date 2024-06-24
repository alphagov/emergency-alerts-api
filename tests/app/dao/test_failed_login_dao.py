from datetime import datetime, timedelta

import pytest

from app.dao.failed_logins_by_ip_dao import (
    dao_create_failed_login_for_ip,
    dao_get_failed_logins,
    dao_get_latest_failed_login_by_ip,
)
from app.errors import InvalidRequest
from app.failed_logins_by_ip.rest import check_failed_login_count_for_ip
from app.models import FailedLoginCountByIP
from tests.app.db import create_failed_login


def test_get_failed_logins_returns_all_failed_logins(notify_db_session):
    dao_create_failed_login_for_ip("192.0.2.15")
    dao_create_failed_login_for_ip("192.0.2.15")
    dao_create_failed_login_for_ip("192.0.2.15")
    response = dao_get_failed_logins()
    assert len(response) == 3


def test_get_latest_failed_logins_returns_latest_failed_login(notify_db_session):
    dao_create_failed_login_for_ip("192.0.2.15")
    failed_login = create_failed_login(
        ip="192.0.2.15", failed_login_count=3, attempted_at=datetime.now() + timedelta(seconds=30)
    )

    response = dao_get_latest_failed_login_by_ip("192.0.2.15")
    assert response.attempted_at == failed_login.attempted_at


def test_get_failed_login_by_ip_returns_none_if_none_found(notify_db_session):
    assert dao_get_failed_logins() == []


def test_check_failed_login_count_for_ip_raises_invalid_request_failed_login_too_soon(
    notify_db_session, admin_request, mocker
):
    for i in range(3):
        failed_login_1 = FailedLoginCountByIP(
            ip="127.0.0.1", failed_login_count=1 + i, attempted_at=datetime.now() + timedelta(seconds=i * 10)
        )
        notify_db_session.add(failed_login_1)
        notify_db_session.commit()
    response = admin_request.get("failed_logins.get_failed_login_by_ip", ip="127.0.0.1")
    assert len(response) == 1
    with pytest.raises(expected_exception=InvalidRequest) as e:
        check_failed_login_count_for_ip()
    assert e.value.message == {"login": ["Logged in too soon after latest failed login"]}
    assert e.value.status_code == 400
