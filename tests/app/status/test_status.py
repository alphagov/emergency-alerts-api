import os

import boto3
import pytest
from flask import json
from moto import mock_aws

from tests.app.db import create_organisation, create_service
from tests.conftest import set_config

aws_region = os.environ.get("AWS_REGION", "eu-west-2")


@pytest.mark.parametrize("path", ["/", "/_api_status"])
# Celery won't be called via the HTTP path (it's via a health check scheduled task)
# but we can assert the CLoudWatch logic respects using the SERVICE param anyway
@pytest.mark.parametrize("service", ["api", "celery"])
@mock_aws
def test_get_status_all_ok(client, notify_db_session, notify_api, service, path):
    with set_config(notify_api, "SERVICE", service):
        response = client.get(path)

    db_version = notify_db_session.execute("SELECT version_num FROM alembic_version").fetchone()[0]

    assert response.status_code == 200
    resp_json = json.loads(response.get_data(as_text=True))
    assert resp_json["status"] == "ok"
    assert resp_json["db_version"] == db_version
    assert resp_json["git_commit"]
    assert resp_json["build_time"]

    cloudwatch = boto3.client("cloudwatch", region_name=aws_region)
    app_metric = cloudwatch.list_metrics()["Metrics"][0]
    assert app_metric["MetricName"] == "AppVersion"
    assert app_metric["Namespace"] == "Emergency Alerts"
    assert {"Name": "Application", "Value": service} in app_metric["Dimensions"]

    db_metric = cloudwatch.list_metrics()["Metrics"][1]
    assert db_metric["MetricName"] == "DBVersion"
    assert db_metric["Namespace"] == "Emergency Alerts"
    assert {"Name": "Application", "Value": service} in db_metric["Dimensions"]
    assert {"Name": "Version", "Value": db_version} in db_metric["Dimensions"]


def test_empty_live_service_and_organisation_counts(admin_request):
    assert admin_request.get("status.live_service_and_organisation_counts") == {
        "organisations": 0,
        "services": 0,
    }


def test_populated_live_service_and_organisation_counts(admin_request):
    # Org 1 has three real live services and one fake, for a total of 3
    org_1 = create_organisation("org 1")
    live_service_1 = create_service(service_name="1")
    live_service_1.organisation = org_1
    live_service_2 = create_service(service_name="2")
    live_service_2.organisation = org_1
    live_service_3 = create_service(service_name="3")
    live_service_3.organisation = org_1
    fake_live_service_1 = create_service(service_name="f1")
    fake_live_service_1.organisation = org_1
    inactive_service_1 = create_service(service_name="i1", active=False)
    inactive_service_1.organisation = org_1

    # This service isn’t associated to an org, but should still be counted as live
    create_service(service_name="4")

    # Org 2 has no real live services
    org_2 = create_organisation("org 2")
    trial_service_1 = create_service(service_name="t1", restricted=True)
    trial_service_1.organisation = org_2
    fake_live_service_2 = create_service(service_name="f2")
    fake_live_service_2.organisation = org_2
    inactive_service_2 = create_service(service_name="i2", active=False)
    inactive_service_2.organisation = org_2

    # Org 2 has no services at all
    create_organisation("org 3")

    # These services aren’t associated with an org
    create_service(service_name="f3")
    create_service(service_name="t", restricted=True)
    create_service(service_name="i", restricted=False)

    assert admin_request.get("status.live_service_and_organisation_counts") == {
        "organisations": 2,
        "services": 8,
    }
