import os
from flask import Blueprint, jsonify, request

from app import db, version
from app.dao.organisation_dao import dao_count_organisations_with_live_services
from app.dao.services_dao import dao_count_live_services

status = Blueprint("status", __name__)


@status.route("/", methods=["GET"])
@status.route("/_api_status", methods=["GET", "POST"])
def show_api_status():
    if request.args.get("simple", None):
        return jsonify(status="ok"), 200
    else:
        return (
            jsonify(
                status="ok",  # This should be considered part of the public API
                git_commit=version.__git_commit__,
                build_time=version.__time__,
                db_version=get_db_version(),
                app_version=get_app_version(),
            ),
            200,
        )


@status.route("/_celery_status", methods=["GET", "POST"])
def show_celery_status():
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
                app_version=get_app_version(),
            ),
            200,
        )


@status.route("/_api_status/live-service-and-organisation-counts")
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


def get_app_version():
    if os.getenv("APP_VERSION") is not None:
        return os.getenv("APP_VERSION")
    else:
        return "0.0.0"
