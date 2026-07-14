import boto3
from flask import Blueprint, jsonify

from app import current_app, db, version
from app.authentication.auth import requires_admin_auth
from app.dao.organisation_dao import dao_count_organisations_with_live_services
from app.dao.services_dao import dao_count_live_services
from app.errors import register_errors

status = Blueprint("status", __name__)

register_errors(status)


@status.route("/", methods=["GET"])
@status.route("/_api_status", methods=["GET", "POST"])
def fast_api_status():
    # Unauthenticated liveness probe used by load balancers / uptime checks: no DB, no metadata.
    return jsonify(status="ok"), 200  # This should be considered part of the public API


@status.route("/_api_status/full", methods=["GET"])
def full_api_status():
    # Full status exposes build/version/schema metadata, so it is restricted to authenticated
    # internal callers (e.g. the admin app). The status blueprint is otherwise unauthenticated.
    requires_admin_auth()
    return (
        jsonify(
            status="ok",
            git_commit=version.git_commit,
            build_time=version.time,
            db_version=get_db_version(),
            app_version=version.app_version,
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


def post_app_version_to_cloudwatch():
    try:
        boto3.client("cloudwatch").put_metric_data(
            MetricData=[
                {
                    "MetricName": "AppVersion",
                    "Dimensions": [
                        {
                            "Name": "Application",
                            "Value": current_app.config["SERVICE"],
                        },
                        {
                            "Name": "Version",
                            "Value": version.app_version,
                        },
                    ],
                    "Unit": "Count",
                    "Value": 1,
                }
            ],
            Namespace="Emergency Alerts",
        )
    except Exception:
        current_app.logger.exception("Couldn't post app version to CloudWatch. App version: %s", version.app_version)


def post_db_version_to_cloudwatch(db_version: str):
    try:
        boto3.client("cloudwatch").put_metric_data(
            MetricData=[
                {
                    "MetricName": "DBVersion",
                    "Dimensions": [
                        {
                            "Name": "Application",
                            "Value": current_app.config["SERVICE"],
                        },
                        {
                            "Name": "Version",
                            "Value": db_version,
                        },
                    ],
                    "Unit": "Count",
                    "Value": 1,
                }
            ],
            Namespace="Emergency Alerts",
        )
    except Exception:
        current_app.logger.exception("Couldn't post DB version to CloudWatch. DB version: %s", db_version)
