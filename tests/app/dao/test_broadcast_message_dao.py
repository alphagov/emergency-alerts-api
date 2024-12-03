from datetime import datetime, timedelta

from app.dao.broadcast_message_dao import (
    create_broadcast_provider_message,
    dao_get_all_broadcast_messages,
    dao_get_all_pre_broadcast_messages,
    dao_get_broadcast_message_by_id_and_service_id_with_user,
    dao_get_broadcast_messages_for_service_with_user,
    dao_purge_old_broadcast_messages,
    get_earlier_events_for_broadcast_event,
)
from app.dao.broadcast_service_dao import (
    insert_or_update_service_broadcast_settings,
)
from app.models import (
    BROADCAST_TYPE,
    BroadcastEventMessageType,
    BroadcastMessage,
    BroadcastStatusType,
)
from tests.app.db import create_broadcast_event, create_broadcast_message
from tests.app.db import (
    create_broadcast_provider_message as create_broadcast_provider_message_test,
)
from tests.app.db import create_service, create_template


def test_get_earlier_events_for_broadcast_event(sample_service):
    t = create_template(sample_service, BROADCAST_TYPE)
    bm = create_broadcast_message(t)

    events = [
        create_broadcast_event(
            bm,
            sent_at=datetime(2020, 1, 1, 12, 0, 0),
            message_type=BroadcastEventMessageType.ALERT,
            transmitted_content={"body": "Initial content"},
        ),
        create_broadcast_event(
            bm,
            sent_at=datetime(2020, 1, 1, 13, 0, 0),
            message_type=BroadcastEventMessageType.UPDATE,
            transmitted_content={"body": "Updated content"},
        ),
        create_broadcast_event(
            bm,
            sent_at=datetime(2020, 1, 1, 14, 0, 0),
            message_type=BroadcastEventMessageType.UPDATE,
            transmitted_content={"body": "Updated content"},
            transmitted_areas=["wales"],
        ),
        create_broadcast_event(
            bm,
            sent_at=datetime(2020, 1, 1, 15, 0, 0),
            message_type=BroadcastEventMessageType.CANCEL,
            transmitted_finishes_at=datetime(2020, 1, 1, 15, 0, 0),
        ),
    ]

    # only fetches earlier events, and they're in time order
    earlier_events = get_earlier_events_for_broadcast_event(events[2].id)
    assert earlier_events == [events[0], events[1]]


def test_create_broadcast_provider_message_creates_in_correct_state(sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)
    broadcast_message = create_broadcast_message(t)
    broadcast_event = create_broadcast_event(
        broadcast_message,
        sent_at=datetime(2020, 1, 1, 12, 0, 0),
        message_type=BroadcastEventMessageType.ALERT,
        transmitted_content={"body": "Initial content"},
    )

    broadcast_provider_message = create_broadcast_provider_message(broadcast_event, "fake-provider")

    assert broadcast_provider_message.status == "sending"
    assert broadcast_provider_message.broadcast_event_id == broadcast_event.id
    assert broadcast_provider_message.created_at is not None
    assert broadcast_provider_message.updated_at is None


def test_dao_get_all_broadcast_messages(sample_broadcast_service):
    template_1 = create_template(sample_broadcast_service, BROADCAST_TYPE)
    # older message, should appear second in list
    broadcast_message_1 = create_broadcast_message(
        template_1, starts_at=datetime(2021, 6, 15, 12, 0, 0), status="cancelled"
    )

    service_2 = create_service(service_name="broadcast service 2", service_permissions=[BROADCAST_TYPE])
    insert_or_update_service_broadcast_settings(service_2, channel="severe")

    template_2 = create_template(service_2, BROADCAST_TYPE)
    # newer message, should appear first in list
    broadcast_message_2 = create_broadcast_message(
        template_2,
        stubbed=False,
        status="broadcasting",
        starts_at=datetime(2021, 6, 20, 12, 0, 0),
    )

    # broadcast_message_stubbed
    create_broadcast_message(
        template_2,
        stubbed=True,
        status="broadcasting",
        starts_at=datetime(2021, 6, 15, 12, 0, 0),
    )
    # broadcast_message_old
    create_broadcast_message(
        template_2,
        stubbed=False,
        status="completed",
        starts_at=datetime(2021, 5, 20, 12, 0, 0),
    )
    # broadcast_message_rejected
    create_broadcast_message(
        template_2,
        stubbed=False,
        status="rejected",
        starts_at=datetime(2021, 6, 15, 12, 0, 0),
    )

    broadcast_messages = dao_get_all_broadcast_messages()
    assert len(broadcast_messages) == 2
    assert broadcast_messages == [
        (
            broadcast_message_2.id,
            None,
            "severe",
            "Dear Sir/Madam, Hello. Yours Truly, The Government.",
            {"ids": [], "simple_polygons": []},
            "broadcasting",
            datetime(2021, 6, 20, 12, 0),
            None,
            None,
            None,
        ),
        (
            broadcast_message_1.id,
            None,
            "severe",
            "Dear Sir/Madam, Hello. Yours Truly, The Government.",
            {"ids": [], "simple_polygons": []},
            "cancelled",
            datetime(2021, 6, 15, 12, 0),
            None,
            None,
            None,
        ),
    ]


def test_dao_purge_old_broadcast_messages(sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)

    baseline_message_count = len(dao_get_all_pre_broadcast_messages())

    broadcast_messages = [
        create_broadcast_message(
            t,
            created_at=datetime(2023, 10, 8, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.PENDING_APPROVAL,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2023, 12, 9, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.PENDING_APPROVAL,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 10, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.PENDING_APPROVAL,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 12, 15, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.PENDING_APPROVAL,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 13, 9, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.PENDING_APPROVAL,
        ),
    ]

    test_message_count = len(dao_get_all_pre_broadcast_messages())
    assert test_message_count == baseline_message_count + 5

    # purge all messages older than the two most recent
    older_than = (datetime.now() - datetime(2024, 1, 11)).days

    messages_purged_count = dao_purge_old_broadcast_messages(str(sample_broadcast_service.id), older_than)
    remaining_messages = dao_get_all_pre_broadcast_messages()

    assert messages_purged_count["msgs"] == test_message_count - len(remaining_messages)
    assert messages_purged_count["events"] == 0  # no events yet for pre-broadcast messages

    # expect that the first 3 of our test messages have been purged
    expected_remaining_messages_ids = [str(broadcast_messages[3].id), str(broadcast_messages[4].id)]

    # To get ID, we need to cast the first element of the row tuple to a string
    # [
    #     (UUID('d8946a4e-f7a2-4c39-9187-e15f328590d3'), datetime.datetime(2024, 1, 12, 9, 0), ... ),
    #     (UUID('03cf5d86-7da2-4300-b3cc-ed92612e8cfd'), datetime.datetime(2024, 1, 11, 15, 0), ...)
    # ]
    assert str(remaining_messages[0][0]) in expected_remaining_messages_ids
    assert str(remaining_messages[1][0]) in expected_remaining_messages_ids


def test_dao_purge_old_broadcast_messages_and_broadcast_events(sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)

    baseline_message_count = len(dao_get_all_broadcast_messages())

    broadcast_messages = [
        create_broadcast_message(
            t,
            created_at=datetime(2023, 10, 8, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.BROADCASTING,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2023, 12, 9, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.CANCELLED,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 10, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.BROADCASTING,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 12, 15, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.BROADCASTING,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 13, 9, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.BROADCASTING,
        ),
    ]

    for bm in broadcast_messages:
        create_broadcast_event(
            bm,
            sent_at=bm.starts_at + timedelta(minutes=1),
            message_type=BroadcastEventMessageType.ALERT,
            transmitted_content={"body": "Initial content"},
        )
        if bm.status == "cancelled":
            create_broadcast_event(
                bm,
                sent_at=bm.starts_at + timedelta(minutes=2),
                message_type=BroadcastEventMessageType.CANCEL,
                transmitted_finishes_at=bm.starts_at + timedelta(minutes=2),
            )

    test_message_count = len(dao_get_all_broadcast_messages())
    assert test_message_count == baseline_message_count + 5

    # purge all messages older than the two most recent
    older_than = (datetime.now() - datetime(2024, 1, 11)).days

    messages_purged_count = dao_purge_old_broadcast_messages(str(sample_broadcast_service.id), older_than)
    remaining_messages = dao_get_all_broadcast_messages()

    assert messages_purged_count["msgs"] == test_message_count - len(remaining_messages)
    assert messages_purged_count["events"] == 4

    # expect that the first 3 of our test messages have been purged
    expected_remaining_messages_ids = [str(broadcast_messages[3].id), str(broadcast_messages[4].id)]

    assert str(remaining_messages[0][0]) in expected_remaining_messages_ids
    assert str(remaining_messages[1][0]) in expected_remaining_messages_ids


def test_dao_purge_old_broadcastmessages_events_providermessages_and_providermessagenumbers(sample_broadcast_service):
    t = create_template(sample_broadcast_service, BROADCAST_TYPE)

    baseline_message_count = len(dao_get_all_broadcast_messages())

    broadcast_messages = [
        create_broadcast_message(
            t,
            created_at=datetime(2023, 10, 8, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.BROADCASTING,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2023, 10, 15, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.CANCELLED,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2023, 12, 9, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.CANCELLED,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 10, 12, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.BROADCASTING,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 12, 15, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.BROADCASTING,
        ),
        create_broadcast_message(
            t,
            created_at=datetime(2024, 1, 13, 9, 0, 0),
            starts_at=datetime.now(),
            status=BroadcastStatusType.BROADCASTING,
        ),
    ]

    for bm in broadcast_messages:
        be1 = create_broadcast_event(
            bm,
            sent_at=bm.starts_at + timedelta(minutes=1),
            message_type=BroadcastEventMessageType.ALERT,
            transmitted_content={"body": "Initial content"},
        )
        create_broadcast_provider_message_test(be1, "ee", status="returned-ack")
        create_broadcast_provider_message_test(be1, "vodafone", status="returned-ack")
        if bm.status == "cancelled":
            be2 = create_broadcast_event(
                bm,
                sent_at=bm.starts_at + timedelta(minutes=2),
                message_type=BroadcastEventMessageType.CANCEL,
                transmitted_finishes_at=bm.starts_at + timedelta(minutes=2),
            )
            create_broadcast_provider_message_test(be2, "ee", status="returned-ack")
            create_broadcast_provider_message_test(be2, "vodafone", status="returned-ack")

    test_message_count = len(dao_get_all_broadcast_messages())
    assert test_message_count == baseline_message_count + 6

    # purge all messages older than the two most recent
    older_than = (datetime.now() - datetime(2024, 1, 11)).days

    purged_count = dao_purge_old_broadcast_messages(str(sample_broadcast_service.id), older_than)
    remaining_messages = dao_get_all_broadcast_messages()

    assert purged_count["msgs"] == test_message_count - len(remaining_messages)
    assert purged_count["events"] == 6
    assert purged_count["provider_msgs"] == 12
    assert purged_count["msg_numbers"] == 6

    # expect that the first 3 of our test messages have been purged
    expected_remaining_messages_ids = [str(broadcast_messages[4].id), str(broadcast_messages[5].id)]

    assert str(remaining_messages[0][0]) in expected_remaining_messages_ids
    assert str(remaining_messages[1][0]) in expected_remaining_messages_ids


def test_dao_get_broadcast_message_by_id_and_service_id_with_user(sample_broadcast_service):
    template_1 = create_template(sample_broadcast_service, "broadcast")
    message = create_broadcast_message(
        template_1,
        stubbed=False,
        status="broadcasting",
        starts_at=datetime(2021, 6, 20, 12, 0, 0),
    )
    broadcast_message = dao_get_broadcast_message_by_id_and_service_id_with_user(
        message.id, sample_broadcast_service.id
    )
    assert broadcast_message == {}


def test_dao_get_broadcast_messages_for_service_with_user(sample_broadcast_service):
    template_1 = create_template(sample_broadcast_service, "broadcast")
    create_broadcast_message(
        template_1,
        stubbed=False,
        status="broadcasting",
        starts_at=datetime(2021, 6, 20, 12, 0, 0),
    )
    create_broadcast_message(
        template_1,
        stubbed=False,
        status="broadcasting",
        starts_at=datetime(2021, 6, 20, 12, 0, 0),
    )
    broadcast_messages = dao_get_broadcast_messages_for_service_with_user(sample_broadcast_service.id)
    assert len(broadcast_messages) == 3
    assert isinstance(broadcast_messages[0][0], BroadcastMessage)
