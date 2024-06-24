import datetime
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
    url_prefix="/failed_logins",
)

register_errors(failed_logins_by_ip_blueprint)


@failed_logins_by_ip_blueprint.route("")
def get_all_failed_logins():
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_failed_logins()
    data = [obj.serialize() for obj in data] if data else []
    return jsonify(data or {}), 200


@failed_logins_by_ip_blueprint.route("")
def get_failed_login_by_ip():
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_latest_failed_login_by_ip(ip)
    return jsonify(data.serialize() if data else {}), 200


@failed_logins_by_ip_blueprint.route("")
def create_failed_login_for_ip():
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_create_failed_login_for_ip(ip)
    return jsonify(data.serialize() if data else {}), 200


@failed_logins_by_ip_blueprint.route("")
def check_failed_login_count_for_ip():
    ip = get_ip_address()
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_latest_failed_login_by_ip(ip)
    failed_login_timestamp = data.attempted_at
    failed_login_count = data.failed_login_count
    current_time = datetime.datetime.now()
    delay_period = calculate_delay_period(failed_login_count)
    if current_time - failed_login_timestamp < timedelta(seconds=delay_period):
        errors = {"login": ["Logged in too soon after latest failed login"]}
        raise InvalidRequest(errors, status_code=400)
