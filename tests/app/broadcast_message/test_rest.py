import re
import uuid

import pytest
from freezegun import freeze_time

from app.dao.broadcast_message_dao import (
    dao_get_broadcast_message_by_id_and_service_id,
)
from app.dao.broadcast_message_history_dao import (
    dao_get_latest_broadcast_message_version_number_by_id_and_service_id,
)
from app.models import (
    BROADCAST_TYPE,
    BroadcastEventMessageType,
    BroadcastStatusType,
)
from tests.app.db import (
    create_broadcast_event,
    create_broadcast_message,
    create_broadcast_provider_message,
    create_service,
    create_template,
    create_user,
)


def test_get_broadcast_message(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE, content="This is a test")
    bm = create_broadcast_message(
        t,
        areas={
            "ids": ["place A", "region B"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
        },
    )

    response = admin_request.get(
        "broadcast_message.get_broadcast_message",
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["id"] == str(bm.id)
    assert response["template_id"] == str(t.id)
    assert response["content"] == "This is a test"
    assert response["template_name"] == t.name
    assert response["status"] == BroadcastStatusType.DRAFT
    assert response["created_at"] is not None
    assert response["starts_at"] is None
    assert response["areas"]["ids"] == ["place A", "region B"]
    assert response["areas"]["simple_polygons"] == [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]]


def test_get_broadcast_message_with_user(mocker, admin_request, sample_broadcast_service, sample_user):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE, content="This is a test")
    bm = create_broadcast_message(
        t,
        areas={
            "ids": ["place A", "region B"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
        },
    )

    response = admin_request.get(
        "broadcast_message.get_broadcast_message_by_id_and_service",
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["id"] == str(bm.id)
    assert response["template_id"] == str(t.id)
    assert response["content"] == "This is a test"
    assert response["template_name"] == t.name
    assert response["status"] == BroadcastStatusType.DRAFT
    assert response["created_at"] is not None
    assert response["starts_at"] is None
    assert response["areas"]["ids"] == ["place A", "region B"]
    assert response["areas"]["simple_polygons"] == [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]]
    assert response["created_by"] == sample_user.name
    assert response["rejected_by"] is None


def test_get_broadcast_provider_messages(admin_request, sample_broadcast_service):
    bm = create_broadcast_message(
        service=sample_broadcast_service,
        content="emergency broadcast content",
        areas={
            "ids": ["place A", "region B"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
        },
    )
    be = create_broadcast_event(broadcast_message=bm)
    mnos = ["ee", "o2", "three", "vodafone"]
    provider_messages = []
    for mno in mnos:
        bpm = create_broadcast_provider_message(broadcast_event=be, provider=mno)
        provider_messages.append({"id": str(bpm.id), "provider": mno})

    response = admin_request.get(
        "broadcast_message.get_broadcast_provider_messages",
        service_id=sample_broadcast_service.id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    response_items = [{key: item[key] for key in ["id", "provider"]} for item in response["messages"]]

    assert provider_messages == response_items


def test_get_broadcast_message_without_template(admin_request, sample_broadcast_service):
    bm = create_broadcast_message(
        service=sample_broadcast_service,
        content="emergency broadcast content",
        areas={
            "ids": ["place A", "region B"],
            "simple_polygons": [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]],
        },
    )

    response = admin_request.get(
        "broadcast_message.get_broadcast_message",
        service_id=sample_broadcast_service.id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["id"] == str(bm.id)
    assert response["template_id"] is None
    assert response["template_version"] is None
    assert response["template_name"] is None
    assert response["content"] == "emergency broadcast content"
    assert response["status"] == BroadcastStatusType.DRAFT
    assert response["created_at"] is not None
    assert response["starts_at"] is None
    assert response["areas"]["ids"] == ["place A", "region B"]
    assert response["areas"]["simple_polygons"] == [[[50.1, 1.2], [50.12, 1.2], [50.13, 1.2]]]
    assert response["personalisation"] is None


def test_get_broadcast_message_with_event(admin_request, sample_broadcast_service):
    bm = create_broadcast_message(
        service=sample_broadcast_service,
        content="emergency broadcast content",
        cap_event="001 example event",
    )

    response = admin_request.get(
        "broadcast_message.get_broadcast_message",
        service_id=sample_broadcast_service.id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["cap_event"] == "001 example event"


def test_get_broadcast_message_404s_if_message_doesnt_exist(admin_request, sample_broadcast_service):
    err = admin_request.get(
        "broadcast_message.get_broadcast_message",
        service_id=sample_broadcast_service.id,
        broadcast_message_id=uuid.uuid4(),
        _expected_status=404,
    )
    assert err == {"message": "No result found", "result": "error"}


def test_get_broadcast_message_404s_if_message_is_for_different_service(admin_request, sample_broadcast_service):
    other_service = create_service(service_name="other")
    other_template = create_template(other_service, BROADCAST_TYPE)
    bm = create_broadcast_message(other_template)

    err = admin_request.get(
        "broadcast_message.get_broadcast_message",
        service_id=sample_broadcast_service.id,
        broadcast_message_id=bm.id,
        _expected_status=404,
    )
    assert err == {"message": "No result found", "result": "error"}


@freeze_time("2020-01-01")
def test_get_broadcast_messages_for_service(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)

    with freeze_time("2020-01-01 12:00"):
        bm1 = create_broadcast_message(t)
    with freeze_time("2020-01-01 13:00"):
        bm2 = create_broadcast_message(t)

    response = admin_request.get(
        "broadcast_message.get_broadcast_messages_for_service", service_id=t.service_id, _expected_status=200
    )

    assert response["broadcast_messages"][0]["id"] == str(bm1.id)
    assert response["broadcast_messages"][1]["id"] == str(bm2.id)


@freeze_time("2020-01-01")
def test_get_broadcast_messages_for_service_with_user(
    admin_request, sample_broadcast_service, sample_broadcast_service_3, sample_user, sample_user_2
):
    """
    This test involves the creation of multiple messages across 2 different services
    and asserting that the responses are as we'd expect.
    """
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    t_2 = create_template(sample_broadcast_service_3, BROADCAST_TYPE)

    with freeze_time("2020-01-01 12:00"):
        bm1 = create_broadcast_message(t)
    with freeze_time("2020-01-01 13:00"):
        bm2 = create_broadcast_message(t)
    with freeze_time("2020-01-01 13:00"):
        bm3 = create_broadcast_message(t_2)

    # Getting all Broadcast messages from first sample service and making relevant assertions
    response_service_1 = admin_request.get(
        "broadcast_message.get_broadcast_msgs_for_service", service_id=t.service_id, _expected_status=200
    )
    assert len(response_service_1["broadcast_messages"]) == 2
    assert response_service_1["broadcast_messages"][0]["id"] == str(bm1.id)
    assert response_service_1["broadcast_messages"][1]["id"] == str(bm2.id)
    assert response_service_1["broadcast_messages"][0]["created_by"] == sample_user.name

    # Getting all Broadcast messages from second sample service and making relevant assertions
    response_service_2 = admin_request.get(
        "broadcast_message.get_broadcast_msgs_for_service", service_id=t_2.service_id, _expected_status=200
    )

    assert len(response_service_2["broadcast_messages"]) == 1
    assert response_service_2["broadcast_messages"][0]["created_by"] == sample_user_2.name
    assert response_service_2["broadcast_messages"][0]["id"] == str(bm3.id)


@freeze_time("2020-01-01")
@pytest.mark.parametrize("training_mode_service", [True, False])
def test_create_broadcast_message(admin_request, sample_broadcast_service, training_mode_service):
    sample_broadcast_service.restricted = training_mode_service
    t = create_template(
        sample_broadcast_service,
        BROADCAST_TYPE,
        content="Some content\r\n€ŷŵ~\r\n‘’“”—–-",
    )

    response = admin_request.post(
        "broadcast_message.create_broadcast_message",
        _data={
            "template_id": str(t.id),
            "service_id": str(t.service_id),
            "created_by": str(t.created_by_id),
            "areas": {"ids": ["manchester"], "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]]},
        },
        service_id=t.service_id,
        _expected_status=201,
    )

    assert response["template_name"] == t.name
    assert response["status"] == BroadcastStatusType.DRAFT
    assert response["created_at"] is not None
    assert response["created_by_id"] == str(t.created_by_id)
    assert response["personalisation"] == {}
    assert response["areas"] == {
        "ids": ["manchester"],
        "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]],
    }
    assert response["content"] == "Some content\n€ŷŵ~\n''\"\"---"

    broadcast_message = dao_get_broadcast_message_by_id_and_service_id(response["id"], sample_broadcast_service.id)
    assert broadcast_message.stubbed == training_mode_service

    broadcast_message_version = dao_get_latest_broadcast_message_version_number_by_id_and_service_id(
        broadcast_message.id, sample_broadcast_service.id
    )
    assert broadcast_message_version.reference == t.name
    assert broadcast_message_version.created_by_id == t.created_by_id
    assert broadcast_message_version.created_at is not None
    assert broadcast_message_version.version == 1
    assert broadcast_message_version.areas == {
        "ids": ["manchester"],
        "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]],
    }


@pytest.mark.parametrize(
    "data, expected_errors",
    [
        (
            {},
            [
                {"error": "ValidationError", "message": "service_id is a required property"},
                {"error": "ValidationError", "message": "created_by is a required property"},
                {"error": "ValidationError", "message": "{} is not valid under any of the given schemas"},
            ],
        ),
        (
            {
                "template_id": str(uuid.uuid4()),
                "service_id": str(uuid.uuid4()),
                "created_by": str(uuid.uuid4()),
                "foo": "something else",
            },
            [{"error": "ValidationError", "message": "Additional properties are not allowed (foo was unexpected)"}],
        ),
    ],
)
def test_create_broadcast_message_400s_if_json_schema_fails_validation(
    admin_request, sample_broadcast_service, data, expected_errors
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)

    response = admin_request.post(
        "broadcast_message.create_broadcast_message", _data=data, service_id=t.service_id, _expected_status=400
    )
    assert response["errors"] == expected_errors


@pytest.mark.parametrize(
    "content, expected_status, expected_errors",
    (
        ("a", 201, None),
        ("a" * 1_395, 201, None),
        ("a\r\n" * 697, 201, None),  # 1,394 chars – new lines normalised to \n
        ("a" * 1_396, 400, ("Content must be 1,395 characters or fewer")),
        ("ŵ" * 615, 201, None),
        ("ŵ" * 616, 400, ("Content must be 615 characters or fewer " "(because it could not be GSM7 encoded)")),
    ),
)
def test_create_broadcast_message_400s_if_content_too_long(
    admin_request,
    sample_broadcast_service,
    content,
    expected_status,
    expected_errors,
):
    response = admin_request.post(
        "broadcast_message.create_broadcast_message",
        service_id=sample_broadcast_service.id,
        _data={
            "service_id": str(sample_broadcast_service.id),
            "created_by": str(sample_broadcast_service.created_by_id),
            "reference": "abc123",
            "content": content,
        },
        _expected_status=expected_status,
    )
    assert response.get("message") == expected_errors


@freeze_time("2020-01-01")
def test_create_broadcast_message_can_be_created_from_content(admin_request, sample_broadcast_service):
    response = admin_request.post(
        "broadcast_message.create_broadcast_message",
        _data={
            "content": "Some content\r\n€ŷŵ~\r\n‘’“”—–-",
            "reference": "abc123",
            "service_id": str(sample_broadcast_service.id),
            "created_by": str(sample_broadcast_service.created_by_id),
        },
        service_id=sample_broadcast_service.id,
        _expected_status=201,
    )
    assert response["content"] == "Some content\n€ŷŵ~\n''\"\"---"
    assert response["reference"] == "abc123"
    assert response["template_id"] is None
    assert response["cap_event"] is None


def test_create_broadcast_message_400s_if_content_and_template_provided(
    admin_request,
    sample_broadcast_service,
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    response = admin_request.post(
        "broadcast_message.create_broadcast_message",
        _data={
            "template_id": str(template.id),
            "content": "Some tailor made broadcast content",
            "service_id": str(sample_broadcast_service.id),
            "created_by": str(sample_broadcast_service.created_by_id),
        },
        service_id=sample_broadcast_service.id,
        _expected_status=400,
    )

    assert len(response["errors"]) == 1
    assert response["errors"][0]["error"] == "ValidationError"
    # The error message for oneOf is ugly, non-deterministic in ordering
    # and contains some UUID, so let’s just pick out the important bits
    assert (" is valid under each of ") in response["errors"][0]["message"]
    assert ("{required: [content]}") in response["errors"][0]["message"]
    assert ("{required: [template_id]}") in response["errors"][0]["message"]


def test_create_broadcast_message_400s_if_reference_and_template_provided(
    admin_request,
    sample_broadcast_service,
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    response = admin_request.post(
        "broadcast_message.create_broadcast_message",
        _data={
            "template_id": str(template.id),
            "reference": "abc123",
            "service_id": str(sample_broadcast_service.id),
            "created_by": str(sample_broadcast_service.created_by_id),
        },
        service_id=sample_broadcast_service.id,
        _expected_status=400,
    )

    assert len(response["errors"]) == 1
    assert response["errors"][0]["error"] == "ValidationError"
    # The error message for oneOf is ugly, non-deterministic in ordering
    # and contains some UUID, so let’s just pick out the important bits
    assert (" is valid under each of ") in response["errors"][0]["message"]
    assert ("{required: [reference]}") in response["errors"][0]["message"]
    assert ("{required: [template_id]}") in response["errors"][0]["message"]


def test_create_broadcast_message_400s_if_reference_not_provided_with_content(
    admin_request,
    sample_broadcast_service,
):
    response = admin_request.post(
        "broadcast_message.create_broadcast_message",
        _data={
            "content": "Some tailor made broadcast content",
            "service_id": str(sample_broadcast_service.id),
            "created_by": str(sample_broadcast_service.created_by_id),
        },
        service_id=sample_broadcast_service.id,
        _expected_status=400,
    )
    assert len(response["errors"]) == 1
    assert response["errors"][0]["error"] == "ValidationError"
    assert response["errors"][0]["message"].endswith("is not valid under any of the given schemas")


def test_create_broadcast_message_400s_if_no_content_or_template(
    admin_request,
    sample_broadcast_service,
):
    response = admin_request.post(
        "broadcast_message.create_broadcast_message",
        _data={
            "service_id": str(sample_broadcast_service.id),
            "created_by": str(sample_broadcast_service.created_by_id),
        },
        service_id=sample_broadcast_service.id,
        _expected_status=400,
    )
    assert len(response["errors"]) == 1
    assert response["errors"][0]["error"] == "ValidationError"
    assert response["errors"][0]["message"].endswith("is not valid under any of the given schemas")


@pytest.mark.parametrize(
    "status",
    [
        BroadcastStatusType.DRAFT,
        BroadcastStatusType.PENDING_APPROVAL,
        BroadcastStatusType.REJECTED,
    ],
)
def test_update_broadcast_message_allows_edit_while_not_yet_live(admin_request, sample_broadcast_service, status):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(
        t,
        areas={"ids": ["manchester"], "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]]},
        status=status,
    )

    response = admin_request.post(
        "broadcast_message.update_broadcast_message",
        _data={
            "reference": "Emergency broadcast",
            "content": "emergency broadcast content",
            "starts_at": "2020-06-01 20:00:01",
            "areas": {"ids": ["london", "glasgow"], "simple_polygons": [[[51.12, 0.2], [50.13, 0.4], [50.14, 0.45]]]},
        },
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["reference"] == "Emergency broadcast"
    assert response["content"] == "emergency broadcast content"
    assert response["starts_at"] == "2020-06-01T20:00:01.000000Z"
    assert response["areas"]["ids"] == ["london", "glasgow"]
    assert response["areas"]["simple_polygons"] == [[[51.12, 0.2], [50.13, 0.4], [50.14, 0.45]]]
    assert response["updated_at"] is not None


@pytest.mark.parametrize(
    "status",
    [
        BroadcastStatusType.BROADCASTING,
        BroadcastStatusType.CANCELLED,
        BroadcastStatusType.COMPLETED,
        BroadcastStatusType.TECHNICAL_FAILURE,
    ],
)
def test_update_broadcast_message_doesnt_allow_edits_after_broadcast_goes_live(
    admin_request, sample_broadcast_service, status
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=status)

    response = admin_request.post(
        "broadcast_message.update_broadcast_message",
        _data={
            "reference": "Emergency broadcast",
            "content": "emergency broadcast content",
            "starts_at": "2020-06-01 20:00:01",
            "areas": {"ids": ["london", "glasgow"], "simple_polygons": [[[51.12, 0.2], [50.13, 0.4], [50.14, 0.45]]]},
        },
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400,
    )
    assert f"status {status}" in response["message"]


def test_update_broadcast_message_sets_finishes_at_separately(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(
        t,
        areas={"ids": ["london"], "simple_polygons": [[[50.12, 1.2], [50.13, 1.2], [50.14, 1.21]]]},
        reference="Test Alert",
    )

    response = admin_request.post(
        "broadcast_message.update_broadcast_message",
        _data={"starts_at": "2020-06-01 20:00:01", "finishes_at": "2020-06-02 20:00:01"},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["starts_at"] == "2020-06-01T20:00:01.000000Z"
    assert response["finishes_at"] == "2020-06-02T20:00:01.000000Z"
    assert response["updated_at"] is not None


@pytest.mark.parametrize(
    "input_dt",
    [
        "2020-06-01 20:00:01",
        "2020-06-01T20:00:01",
        "2020-06-01 20:00:01Z",
        "2020-06-01T20:00:01+00:00",
    ],
)
def test_update_broadcast_message_allows_sensible_datetime_formats(admin_request, sample_broadcast_service, input_dt):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, reference="Test Alert")

    response = admin_request.post(
        "broadcast_message.update_broadcast_message",
        _data={"starts_at": input_dt},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["starts_at"] == "2020-06-01T20:00:01.000000Z"
    assert response["updated_at"] is not None


def test_update_broadcast_message_doesnt_let_you_update_status(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    response = admin_request.post(
        "broadcast_message.update_broadcast_message",
        _data={
            "areas": {
                "ids": ["glasgow"],
                "simple_polygons": [[[55.86, -4.25], [55.85, -4.25], [55.87, -4.24]]],
            },
            "status": BroadcastStatusType.BROADCASTING,
        },
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400,
    )

    assert response["errors"] == [
        {"error": "ValidationError", "message": "Additional properties are not allowed (status was unexpected)"}
    ]


@pytest.mark.parametrize(
    "incomplete_area_data",
    [
        {"areas": {"ids": ["cardiff"]}},
        {"areas": {"simple_polygons": [[[51.28, -3.11], [51.29, -3.12], [51.27, -3.10]]]}},
    ],
)
def test_update_broadcast_message_doesnt_let_you_update_areas_but_not_polygons(
    admin_request, sample_broadcast_service, incomplete_area_data
):
    template = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(template)

    response = admin_request.post(
        "broadcast_message.update_broadcast_message",
        _data=incomplete_area_data,
        service_id=template.service_id,
        broadcast_message_id=broadcast_message.id,
        _expected_status=400,
    )

    assert (
        response["message"]
        == f"Cannot update broadcast_message {broadcast_message.id}, area IDs or polygons are missing."
    )


def test_update_broadcast_message_status(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.DRAFT)

    response = admin_request.post(
        "broadcast_message.update_broadcast_message_status",
        _data={"status": BroadcastStatusType.PENDING_APPROVAL, "created_by": str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["status"] == BroadcastStatusType.PENDING_APPROVAL
    assert response["updated_at"] is not None


def test_update_broadcast_message_status_rejects_with_reason(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.PENDING_APPROVAL)

    response = admin_request.post(
        "broadcast_message.update_broadcast_message_status_with_reason",
        _data={"status": BroadcastStatusType.REJECTED, "rejection_reason": "TEST", "created_by": str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert response["status"] == BroadcastStatusType.REJECTED
    assert response["updated_at"] is not None
    assert response["rejection_reason"] == "TEST"


def test_update_broadcast_message_status_errors_as_missing_reason(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.PENDING_APPROVAL)

    response = admin_request.post(
        "broadcast_message.update_broadcast_message_status_with_reason",
        _data={"status": BroadcastStatusType.REJECTED, "created_by": str(t.created_by_id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400,
    )

    assert response["errors"] == ["Enter the reason for rejecting the alert."]


def test_update_broadcast_message_status_doesnt_let_you_update_other_things(admin_request, sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    response = admin_request.post(
        "broadcast_message.update_broadcast_message_status",
        _data={
            "areas": {"ids": ["glasgow"]},
            "status": BroadcastStatusType.BROADCASTING,
            "created_by": str(t.created_by_id),
        },
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400,
    )

    assert response["errors"] == [
        {
            "error": "ValidationError",
            "message": "Additional properties are not allowed (areas was unexpected)",
        }
    ]


@pytest.mark.parametrize("user_is_platform_admin", [True, False])
def test_update_broadcast_message_allows_service_user_and_platform_admin_to_cancel(
    admin_request, sample_broadcast_service, mocker, user_is_platform_admin
):
    """
    Only platform admins and users belonging to that service should be able to cancel broadcasts.
    """
    t = create_template(sample_broadcast_service, BROADCAST_TYPE, content="emergency broadcast")
    bm = create_broadcast_message(t, status=BroadcastStatusType.BROADCASTING)
    canceller = create_user(email="canceller@gov.uk")
    if user_is_platform_admin:
        canceller.platform_admin = True
    else:
        sample_broadcast_service.users.append(canceller)
    mock_task = mocker.patch("app.celery.broadcast_message_tasks.send_broadcast_event.apply_async")

    response = admin_request.post(
        "broadcast_message.update_broadcast_message_status",
        _data={"status": BroadcastStatusType.CANCELLED, "created_by": str(canceller.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=200,
    )

    assert len(bm.events) == 1
    cancel_event = bm.events[0]

    cancel_id = str(cancel_event.id)

    mock_task.assert_called_once_with(kwargs={"broadcast_event_id": cancel_id}, queue="broadcast-tasks")
    assert response["status"] == BroadcastStatusType.CANCELLED
    assert response["cancelled_at"] is not None
    assert response["cancelled_by_id"] == str(canceller.id)

    assert cancel_event.service_id == sample_broadcast_service.id
    assert cancel_event.transmitted_areas == bm.areas
    assert cancel_event.message_type == BroadcastEventMessageType.CANCEL
    assert cancel_event.transmitted_finishes_at == bm.finishes_at
    assert cancel_event.transmitted_content == {"body": "emergency broadcast"}


def test_update_broadcast_message_status_aborts_if_service_is_suspended(
    admin_request,
    sample_broadcast_service,
):
    bm = create_broadcast_message(service=sample_broadcast_service, content="test")
    sample_broadcast_service.active = False

    admin_request.post(
        "broadcast_message.update_broadcast_message_status",
        _data={"status": BroadcastStatusType.BROADCASTING, "created_by": str(uuid.uuid4())},
        service_id=sample_broadcast_service.id,
        broadcast_message_id=bm.id,
        _expected_status=403,
    )


def test_update_broadcast_message_status_rejects_approval_from_user_not_on_that_service(
    admin_request, sample_broadcast_service, mocker
):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t, status=BroadcastStatusType.PENDING_APPROVAL)
    approver = create_user(email="approver@gov.uk")
    mock_task = mocker.patch("app.celery.broadcast_message_tasks.send_broadcast_event.apply_async")

    response = admin_request.post(
        "broadcast_message.update_broadcast_message_status",
        _data={"status": BroadcastStatusType.BROADCASTING, "created_by": str(approver.id)},
        service_id=t.service_id,
        broadcast_message_id=bm.id,
        _expected_status=400,
    )

    assert mock_task.called is False
    assert "cannot update broadcast" in response["message"]


def test_purge_broadcast_messages(admin_request, sample_broadcast_service, mocker):
    response = admin_request.delete(
        "broadcast_message.purge_broadcast_messages",
        service_id=sample_broadcast_service.id,
        older_than=100,
        _expected_status=200,
    )

    print(response["message"])

    assert re.match(r"Purged (\d+) BroadcastMessage items (.*)", response["message"])
