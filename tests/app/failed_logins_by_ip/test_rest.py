from datetime import datetime

from app.models import FailedLoginCountByIP
from tests.app.test_utils import create_failed_login_for_test


def test_create_failed_login_creates_failed_login(notify_db_session, admin_request, mocker):
    pass


def test_get_all_failed_logins_returns_all_records(notify_db_session, admin_request, mocker):
    failed_login_1 = FailedLoginCountByIP(ip="192.0.2.15", failed_login_count=1, attempted_at=datetime.now())
    failed_login_2 = FailedLoginCountByIP(ip="192.0.2.30", failed_login_count=2, attempted_at=datetime.now())
    notify_db_session.add(failed_login_1)
    notify_db_session.add(failed_login_2)
    notify_db_session.commit()
    response = admin_request.get(
        "failed_logins.get_all_failed_logins",
    )
    assert len(response) == 2
    assert response[0]["ip"] == "192.0.2.15"
    assert response[1]["ip"] == "192.0.2.30"


def test_get_failed_login_by_ip_returns_empty_if_none_found(notify_db_session, admin_request, mocker):
    response = admin_request.get("failed_logins.get_failed_login_by_ip")
    assert len(response) == 0


def test_get_failed_login_by_ip_returns_only_failed_logins(notify_db_session, admin_request, mocker):
    # Creating a failed login record for a different IP address
    create_failed_login_for_test(notify_db_session, "192.0.2.30", 1)
    response = admin_request.get("failed_logins.get_failed_login_by_ip")
    assert len(response) == 0  # Should return 0 as IP for failed login record is different than request IP

    failed_login_2 = FailedLoginCountByIP(ip="127.0.0.1", failed_login_count=1, attempted_at=datetime.now())
    notify_db_session.add(failed_login_2)
    notify_db_session.commit()
    response = admin_request.get("failed_logins.get_failed_login_by_ip")
    assert len(response) == 1
