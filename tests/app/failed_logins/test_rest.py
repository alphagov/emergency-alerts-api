from tests.app.conftest import test_ip_2, test_ip_3
from tests.app.test_utils import create_failed_login_for_test


def test_get_failed_login_for_requester_returns_empty_if_none_found(notify_db_session, admin_request, mocker):
    """
    Asserts that the response for the get_failed_login_for_requester is empty when no failed login attempts
    have been created.
    """
    response = admin_request.get("failed_logins.get_failed_login_for_requester")
    assert response == {}


def test_get_failed_login_for_requester_returns_only_failed_logins_for_ip(notify_db_session, admin_request, mocker):
    """
    Creates a failed login record with a specific IP and then asserts that the response
    from get_failed_login_for_requester route is empty as the IP isn't the same as test IP and thus
    unable to fetch it.
    Then creates a failed login record with test IP and asserts that it is returned in the response
    from get_failed_login_for_requester route.
    """
    create_failed_login_for_test(notify_db_session, test_ip_2)

    response = admin_request.get("failed_logins.get_failed_login_for_requester")
    assert response == {}

    create_failed_login_for_test(notify_db_session, test_ip_3)

    response = admin_request.get("failed_logins.get_failed_login_for_requester")
    assert "ip" in response and response["ip"] == test_ip_3
