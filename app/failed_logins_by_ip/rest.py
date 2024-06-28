from datetime import timedelta

from flask import Blueprint, jsonify

from app.dao.failed_logins_by_ip_dao import (
    dao_create_failed_login_for_ip,
    dao_get_failed_logins,
    dao_get_latest_failed_login_by_ip,
)
from app.errors import InvalidRequest, register_errors
from app.utils import calculate_delay_period, get_ip_address

failed_logins_by_ip_blueprint = Blueprint(
    "failed_logins",
    __name__,
    url_prefix="/failed-logins",
)

register_errors(failed_logins_by_ip_blueprint)


@failed_logins_by_ip_blueprint.route("fetch-all")
def get_all_failed_logins():
    """
    Fetches all failed login records in the table.
    """
    data = dao_get_failed_logins()
    data = [obj.serialize() for obj in data] if data else []
    return jsonify(data or {}), 200


@failed_logins_by_ip_blueprint.route("fetch-for-requester-ip")
def get_failed_login_by_ip():
    """
    Fetches most recent failed login attempt for specific IP address from the table.
    """
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_latest_failed_login_by_ip(ip)
    return jsonify(data.serialize() if data else {}), 200


@failed_logins_by_ip_blueprint.route("check-failed-login-for-requester-ip")
def check_failed_login_count_for_ip():
    """
    Fetches most recent failed login attempt, for specific IP address, from the table and
    determines whether or not it is within calculated throttle period. If the latest
    failed login is recorded within throttle period, an Invalidrequest exception is raised.

    If there have been no previous failed login attempts for this IP, the failed login
    attempt is created and nothing further is checked.
    """
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    if dao_get_latest_failed_login_by_ip(ip) is not None:
        penultimate_failed_login = dao_get_latest_failed_login_by_ip(ip)
        latest_failed_login = dao_create_failed_login_for_ip(ip)

        failed_login_count = penultimate_failed_login.failed_login_count

        delay_period = calculate_delay_period(failed_login_count)
        if latest_failed_login.attempted_at - penultimate_failed_login.attempted_at < timedelta(seconds=delay_period):
            errors = {"login": ["Logged in too soon after latest failed login"]}
            raise InvalidRequest(errors, status_code=400)
    else:
        latest_failed_login = dao_create_failed_login_for_ip(ip)
