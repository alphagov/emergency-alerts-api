import time
from flask import Blueprint, jsonify

from app.dao.failed_login_count_by_ip_dao import (
    dao_get_failed_login_counts_by_ip,
    dao_increment_failed_login_counts_by_ip,
    dao_reset_failed_login_counts_by_ip,
)
from app.errors import InvalidRequest, register_errors

failed_login_count_by_ip_blueprint = Blueprint(
    "failed_login_count_by_ip",
    __name__,
    url_prefix="/ip-failed-login-count",
)

register_errors(failed_login_count_by_ip_blueprint)


@failed_login_count_by_ip_blueprint.route("")
def get_failed_login_count_by_ip(ip):
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_failed_login_counts_by_ip(ip)
    return jsonify(data.serialize() if data else {}), 200


@failed_login_count_by_ip_blueprint.route("")
def increment_failed_login_count_for_ip(ip):
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_failed_login_counts_by_ip(ip)
    dao_increment_failed_login_counts_by_ip(data)
    return jsonify(data.serialize() if data else {}), 200


@failed_login_count_by_ip_blueprint.route("")
def check_failed_login_count_for_ip(ip):
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_failed_login_counts_by_ip(ip)
    if data.failed_login_count > 4:
        time.sleep(120)
    elif 0 < data.failed_login_count < 4:
        time.sleep(10 * (2 ** (data.failed_login_count - 1)))


@failed_login_count_by_ip_blueprint.route("")
def reset_failed_login_count_for_ip(ip):
    if not ip:
        errors = {"ip": ["Missing data for required field."]}
        raise InvalidRequest(errors, status_code=400)
    data = dao_get_failed_login_counts_by_ip(ip)
    dao_reset_failed_login_counts_by_ip(data)
    return jsonify(data.serialize() if data else {}), 200
