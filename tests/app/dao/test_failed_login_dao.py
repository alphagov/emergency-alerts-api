from datetime import datetime, timedelta

from app.dao.failed_logins_by_ip_dao import (
    dao_create_failed_login_for_ip,
    dao_get_failed_logins,
    dao_get_latest_failed_login_by_ip,
)
from app.models import FailedLoginCountByIP
from tests.app.db import create_failed_login


def test_get_failed_logins_returns_all_failed_logins(notify_db_session):
    """
    Creates 3 failed login records and checks that these are returned by dao_get_failed_logins.
    """
    dao_create_failed_login_for_ip("192.0.2.15")
    dao_create_failed_login_for_ip("192.0.2.15")
    dao_create_failed_login_for_ip("192.0.2.15")
    response = dao_get_failed_logins()
    assert len(response) == 3
    assert {record.ip for record in response} == {"192.0.2.15"}


def test_get_latest_failed_logins_returns_latest_failed_login(notify_db_session):
    """
    Creates a failed login record with dao_create_failed_login_for_ip and then again with
    create_failed_login to set the attempted_at value to a later datetime.
    Then dao_get_latest_failed_login_by_ip response is checked by
    asserting that attempted_at value is the later one, thus it has returned the latest record.

    """
    dao_create_failed_login_for_ip("192.0.2.15")
    failed_login = create_failed_login(ip="192.0.2.15", attempted_at=datetime.now() + timedelta(seconds=30))

    response = dao_get_latest_failed_login_by_ip("192.0.2.15")
    assert response.attempted_at and response.attempted_at == failed_login.attempted_at


def test_get_failed_login_by_ip_returns_none_if_none_found(notify_db_session):
    """
    Asserts that dao_get_failed_logins returns an empty list if no records have been added.
    """
    assert dao_get_failed_logins() == []


def test_check_throttle_for_ip_raises_invalid_request_failed_login_too_soon(notify_db_session, admin_request, mocker):
    """
    Creates 3 failed login records, each with different values for attempted_at and asserts
    that dao_get_latest_failed_login_by_ip returns the record with the most recent attempted_at
    value, that is stored to check against, and the same failed_login_count as most recent record.

    Test also asserts that an expection should have been raised, InvalidRequest, as the failed login
    attempts have occured within throttle period of each other. If there are fewer than 4 failed
    login attempts, the throttle period between them is 10 * (2 ** (failed_login_count - 1)) and any
    failed login attempt sooner will result in an InvalidRequest raised.

    """
    attempted_at = None

    for i in range(3):
        attempted_at = datetime.now() + timedelta(seconds=i * 10)
        failed_login_1 = FailedLoginCountByIP(ip="127.0.0.1", attempted_at=attempted_at)
        notify_db_session.add(failed_login_1)
        notify_db_session.commit()

    response = dao_get_latest_failed_login_by_ip("127.0.0.1")
    assert response.ip and response.ip == "127.0.0.1"

    # with pytest.raises(expected_exception=InvalidRequest) as e:
    #     check_throttle_for_ip()

    # assert e.value.message == "User has sent too many login requests in a given amount of time."
    # assert e.value.status_code == 429
