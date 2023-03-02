from app import db, version
from app.dao.organisation_dao import dao_count_organisations_with_live_services
from app.dao.services_dao import dao_count_live_services

from flask import Blueprint, jsonify, request
from os import environ as env_var

status = Blueprint("status", __name__)


@status.route("/", methods=["GET"])
@status.route("/_api_status", methods=["GET", "POST"])
def show_status():
    if request.args.get("simple", None):
        return jsonify(status="ok"), 200
    else:
        return (
            jsonify(
                status="ok",  # This should be considered part of the public API
                git_commit=version.__git_commit__,
                build_time=version.__time__,
                db_version=get_db_version(),
            ),
            200,
        )


@status.route("/", methods=["GET"])
@status.route("/_celery_status", methods=["GET", "POST"])
def show_status():
    if request.args.get("simple", None):
        return jsonify(status="ok"), 200
    else:
        return (
            jsonify(
                # This is a placeholder health check
                # This should be modified to check the celery queue for
                # availability and correctness of function
                status="ok",
                git_commit=version.__git_commit__,
                build_time=version.__time__,
            ),
            200,
        )


@status.route(status_endpoint + "/live-service-and-organisation-counts")
def live_service_and_organisation_counts():
    return (
        jsonify(
            organisations=dao_count_organisations_with_live_services(),
            services=dao_count_live_services(),
        ),
        200,
    )


def get_db_version():
    query = "SELECT version_num FROM alembic_version"
    full_name = db.session.execute(query).fetchone()[0]
    return full_name
