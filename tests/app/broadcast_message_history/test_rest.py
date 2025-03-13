import uuid

from freezegun import freeze_time

from app.utils import get_interval_seconds_or_none
from tests.app.db import create_broadcast_message_version


def test_get_broadcast_message_version(admin_request, sample_service):
    id = uuid.uuid4()

    with freeze_time("2020-01-01 11:00"):
        bmv3 = create_broadcast_message_version(
            service_id=sample_service.id, id=id, version=3, content="Test 3", duration="04:00:00"
        )
    with freeze_time("2020-01-01 12:00"):
        create_broadcast_message_version(service_id=sample_service.id, id=id, version=1, content="Test 1")
    with freeze_time("2020-01-01 13:00"):
        create_broadcast_message_version(
            service_id=sample_service.id, id=id, version=2, content="Test 2", duration="01:00:00"
        )

    response = admin_request.get(
        "broadcast_message_history.get_broadcast_message_version",
        service_id=str(sample_service.id),
        broadcast_message_id=id,
        version=3,
        _expected_status=200,
    )

    assert response["id"] == str(bmv3.id)
    assert response["areas"] == bmv3.areas
    assert response["content"] == bmv3.content
    assert response["reference"] == bmv3.reference
    assert response["duration"] == get_interval_seconds_or_none(bmv3.duration)


@freeze_time("2020-01-01")
def test_get_broadcast_message_versions(admin_request, sample_service):
    id = uuid.uuid4()
    with freeze_time("2020-01-01 12:00"):
        bmv1 = create_broadcast_message_version(service_id=sample_service.id, id=id, version=1)
    with freeze_time("2020-01-01 13:00"):
        bmv2 = create_broadcast_message_version(service_id=sample_service.id, id=id, version=2)

    response = admin_request.get(
        "broadcast_message_history.get_broadcast_message_versions",
        service_id=str(sample_service.id),
        broadcast_message_id=id,
        _expected_status=200,
    )

    assert len(response) == 2
    assert response[0]["id"] == str(bmv1.id)
    assert response[1]["id"] == str(bmv2.id)
    assert response[0]["content"] == bmv1.content == "Test Broadcast Content"
    assert response[1]["content"] == bmv2.content
