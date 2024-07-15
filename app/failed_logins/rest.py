from flask import Blueprint, jsonify

from app.dao.failed_logins_dao import (
    dao_create_failed_login_for_ip,
    dao_get_count_of_all_failed_logins_for_ip,
    dao_get_latest_failed_login_by_ip,
)
from app.errors import InvalidRequest, register_errors
from app.utils import (
    calculate_delay_period,
    check_request_within_throttle_period,
    get_ip_address,
    log_throttled_login,
)

failed_logins_blueprint = Blueprint(
    "failed_logins",
    __name__,
    url_prefix="/failed-logins",
)

register_errors(failed_logins_blueprint)


@failed_logins_blueprint.route("fetch-for-requester")
def get_failed_login_for_requester():
    """
    Fetches most recent failed login attempt for specific IP address from the table.
    """
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_latest_failed_login_by_ip(ip)
    return jsonify(data.serialize() if data else {}), 200


@failed_logins_blueprint.route("check-failed-login-for-requester")
def check_throttle_for_requester(user):
    """
    Firstly checks if IP address should be throttled, then retrieves count of all failed login
    attempts for set period of time.

    If there have been no previous failed login attempts for this IP, then the function
    has an early return and there's no throttle.

    Fetches most recent failed login attempt, for specific IP address, from the table and
    determines whether or not it is within calculated throttle period. If the latest
    failed login is recorded within throttle period, an Invalidrequest exception is raised.
    """
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)

    failed_login_count = dao_get_count_of_all_failed_logins_for_ip(ip)
    if not failed_login_count:
        return

    last_failed_login = dao_get_latest_failed_login_by_ip(ip)
    delay_period = calculate_delay_period(failed_login_count)
    if check_request_within_throttle_period(last_failed_login, delay_period):
        log_throttled_login(user, ip, "User login throttled")
        errors = {"Failed to login": ["User has sent too many login requests in a given amount of time."]}
        raise InvalidRequest(errors, status_code=429)


def add_failed_login_for_requester():
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    dao_create_failed_login_for_ip(ip)
