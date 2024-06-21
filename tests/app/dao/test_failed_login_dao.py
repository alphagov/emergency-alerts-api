from datetime import datetime, timedelta

from app.dao.failed_logins_by_ip_dao import (
    dao_create_failed_login_for_ip,
    dao_get_failed_logins,
    dao_get_latest_failed_login_by_ip,
)
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
