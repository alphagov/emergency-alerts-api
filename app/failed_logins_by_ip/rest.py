import datetime
from datetime import timedelta

from flask import Blueprint, jsonify, request

from app.dao.failed_logins_by_ip_dao import (
    dao_create_failed_login_for_ip,
    dao_get_latest_failed_login_by_ip,
)
from app.errors import InvalidRequest, register_errors

failed_logins_by_ip_blueprint = Blueprint(
    "failed_logins",
    __name__,
    url_prefix="/ip-failed-login-count",
)

register_errors(failed_logins_by_ip_blueprint)


@failed_logins_by_ip_blueprint.route("")
def get_failed_logins_by_ip():
    ip = request.remote_addr
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_latest_failed_login_by_ip(ip)
    return jsonify(data.serialize() if data else {}), 200


@failed_logins_by_ip_blueprint.route("")
def create_failed_login_for_ip():
    ip = request.remote_addr
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_create_failed_login_for_ip(ip)
    return jsonify(data.serialize() if data else {}), 200


@failed_logins_by_ip_blueprint.route("")
def check_failed_login_count_for_ip():
    ip = request.remote_addr
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_latest_failed_login_by_ip(ip)
    failed_login_timestamp = data.attempted_at
    failed_login_count = data.failed_login_count
    current_time = datetime.datetime.now()
    if failed_login_count < 4:
        delay_period = 10 * (2 ** (failed_login_count - 1))
    else:
        delay_period = 120
    if current_time - failed_login_timestamp < timedelta(seconds=delay_period):
        errors = {"password": ["Incorrect password"]}
        print('too soon!')
        raise InvalidRequest(errors, status_code=400)
