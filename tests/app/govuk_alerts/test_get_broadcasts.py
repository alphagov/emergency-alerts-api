from datetime import datetime, timedelta, timezone

import pytest
from flask import current_app, json

from app.models import BROADCAST_TYPE
from tests import create_internal_authorization_header
from tests.app.db import create_broadcast_message, create_template


@pytest.mark.parametrize("channel", ["severe", "government"])
def test_get_filtered_broadcasts_returns_list_of_public_broadcasts_and_200(
    channel, admin_request, client, sample_broadcast_service
):
    # Set up channel
    data = {
        "broadcast_channel": channel,
        "service_mode": "live",
        "provider_restriction": ["ee", "o2", "three", "vodafone"],
    }
    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service.id,
        _data=data,
    )

    template_1 = create_template(sample_broadcast_service, BROADCAST_TYPE)

    broadcast_message_1 = create_broadcast_message(
        template_1, starts_at=datetime(2021, 6, 15, 12, 0, 0), status="cancelled"
    )

    broadcast_message_2 = create_broadcast_message(
        template_1, starts_at=datetime(2021, 6, 22, 12, 0, 0), status="broadcasting"
    )

    jwt_client_id = current_app.config["GOVUK_ALERTS_CLIENT_ID"]
    header = create_internal_authorization_header(jwt_client_id)

    response = client.get("/govuk-alerts", headers=[header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert len(json_response["alerts"]) == 2

    assert json_response["alerts"][0]["id"] == str(broadcast_message_2.id)
    assert json_response["alerts"][0]["starts_at"] == "2021-06-22T12:00:00.000000Z"
    assert json_response["alerts"][0]["finishes_at"] is None
    assert json_response["alerts"][1]["id"] == str(broadcast_message_1.id)
    assert json_response["alerts"][1]["starts_at"] == "2021-06-15T12:00:00.000000Z"


@pytest.mark.parametrize("channel", ["operator", "test"])
def test_get_filtered_broadcasts_returns_non_public_broadcasts_and_200(
    channel, admin_request, client, sample_broadcast_service
):
    # Set up channel
    data = {
        "broadcast_channel": channel,
        "service_mode": "live",
        "provider_restriction": ["ee", "o2", "three", "vodafone"],
    }
    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service.id,
        _data=data,
    )

    template_1 = create_template(sample_broadcast_service, BROADCAST_TYPE)
    older_alert_date = datetime.now(timezone.utc) - timedelta(hours=49)
    newer_alert_date = datetime.now(timezone.utc) - timedelta(hours=47)

    broadcast_message_1 = create_broadcast_message(template_1, starts_at=older_alert_date, status="cancelled")
    broadcast_message_2 = create_broadcast_message(template_1, starts_at=newer_alert_date, status="broadcasting")

    jwt_client_id = current_app.config["GOVUK_ALERTS_CLIENT_ID"]
    header = create_internal_authorization_header(jwt_client_id)

    response = client.get("/govuk-alerts", headers=[header])

    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert len(json_response["alerts"]) == 1

    assert json_response["alerts"][0]["id"] == str(broadcast_message_2.id)
    assert json_response["alerts"][0]["starts_at"] == newer_alert_date.isoformat().replace("+00:00", "Z")
    assert json_response["alerts"][0]["finishes_at"] is None
    assert str(broadcast_message_1.id) not in json.dumps(json_response)


def test_get_all_broadcasts_returns_all_broadcasts_and_200(
    admin_request, client, sample_broadcast_service, sample_broadcast_service_2
):
    # Set up service 1 as severe channel
    data = {
        "broadcast_channel": "severe",
        "service_mode": "live",
        "provider_restriction": ["ee", "o2", "three", "vodafone"],
    }
    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service.id,
        _data=data,
    )
    # Set up service 2 as operator channel
    data = {
        "broadcast_channel": "operator",
        "service_mode": "live",
        "provider_restriction": ["ee", "o2", "three", "vodafone"],
    }
    admin_request.post(
        "service.set_as_broadcast_service",
        service_id=sample_broadcast_service_2.id,
        _data=data,
    )

    template_1 = create_template(sample_broadcast_service, BROADCAST_TYPE)
    template_2 = create_template(sample_broadcast_service_2, BROADCAST_TYPE)

    older_alert_date = datetime.now(timezone.utc) - timedelta(hours=49)
    newer_alert_date = datetime.now(timezone.utc) - timedelta(hours=47)

    broadcast_message_1 = create_broadcast_message(
        template_1, starts_at=datetime(2021, 6, 15, 12, 0, 0), status="cancelled"
    )
    broadcast_message_2 = create_broadcast_message(
        template_1, starts_at=datetime(2021, 6, 22, 12, 0, 0), status="broadcasting"
    )
    broadcast_message_3 = create_broadcast_message(template_2, starts_at=older_alert_date, status="cancelled")
    broadcast_message_4 = create_broadcast_message(template_2, starts_at=newer_alert_date, status="broadcasting")

    jwt_client_id = current_app.config["GOVUK_ALERTS_CLIENT_ID"]
    header = create_internal_authorization_header(jwt_client_id)

    response = client.get("/govuk-alerts/all", headers=[header])
    json_response = json.loads(response.get_data(as_text=True))

    assert response.status_code == 200
    assert len(json_response["alerts"]) == 4

    assert json_response["alerts"][0]["id"] == str(broadcast_message_4.id)
    assert json_response["alerts"][0]["starts_at"] == newer_alert_date.isoformat().replace("+00:00", "Z")
    assert json_response["alerts"][0]["finishes_at"] is None
    assert json_response["alerts"][1]["id"] == str(broadcast_message_3.id)
    assert json_response["alerts"][1]["starts_at"] == older_alert_date.isoformat().replace("+00:00", "Z")
    assert json_response["alerts"][2]["id"] == str(broadcast_message_2.id)
    assert json_response["alerts"][2]["starts_at"] == "2021-06-22T12:00:00.000000Z"
    assert json_response["alerts"][2]["finishes_at"] is None
    assert json_response["alerts"][3]["id"] == str(broadcast_message_1.id)
    assert json_response["alerts"][3]["starts_at"] == "2021-06-15T12:00:00.000000Z"
