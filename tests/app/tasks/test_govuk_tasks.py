from datetime import datetime, timedelta
from unittest.mock import ANY

import pytz

from app.models import (
    PublishTaskProgress,
)
from app.tasks.govuk_tasks import publish_govuk_build, publish_govuk_build_full


def test_publish_schedules_when_no_pending_tasks_present(mocker, notify_api):
    mocker.patch(
        "app.tasks.govuk_tasks.dao_get_all_pending_publish_tasks",
        return_value=[],
    )
    created_pending = PublishTaskProgress(id="created-pending")
    mock_create = mocker.patch("app.tasks.govuk_tasks.dao_create_publish_task", return_value=created_pending)
    mock_send = mocker.patch("app.tasks.govuk_tasks._publish_govuk_alerts.send", return_value="send")

    create, send = publish_govuk_build("test")

    assert create == created_pending
    assert send == "send"
    mock_create.assert_called_once_with("publish-dynamic", "pending", trace_id=ANY)
    mock_send.assert_called_once_with(pending_progress_id="created-pending", broadcast_event_id="test")


def test_publish_still_schedules_when_old_pending_tasks_present(mocker, notify_api):
    mocker.patch(
        "app.tasks.govuk_tasks.dao_get_all_pending_publish_tasks",
        return_value=[
            # Over 10 minutes old: beyond the (default) cutoff in config.py
            PublishTaskProgress(started_at=datetime.now(pytz.utc) - timedelta(minutes=5))
        ],
    )
    created_pending = PublishTaskProgress(id="created-pending")
    mock_create = mocker.patch("app.tasks.govuk_tasks.dao_create_publish_task", return_value=created_pending)
    mock_send = mocker.patch("app.tasks.govuk_tasks._publish_govuk_alerts.send", return_value="send")

    create, send = publish_govuk_build("test")

    assert create == created_pending
    assert send == "send"
    mock_create.assert_called_once_with("publish-dynamic", "pending", trace_id=ANY)
    mock_send.assert_called_once_with(pending_progress_id="created-pending", broadcast_event_id="test")


def test_does_not_schedule_when_pending_tasks_present(mocker, notify_api):
    progress_task = PublishTaskProgress(task_id="publish-dynamic", started_at=datetime.now(pytz.utc))
    mocker.patch(
        "app.tasks.govuk_tasks.dao_get_all_pending_publish_tasks",
        return_value=[progress_task],
    )
    mock_create = mocker.patch("app.tasks.govuk_tasks.dao_create_publish_task", return_value="created-pending")
    mock_send = mocker.patch("app.tasks.govuk_tasks._publish_govuk_alerts.send", return_value="send")

    ret = publish_govuk_build()
    assert ret == (progress_task, None)

    mock_create.assert_not_called()
    mock_send.assert_not_called()


def test_full_publish_always_schedules_and_deletes_pending(mocker, notify_api):
    mock_delete = mocker.patch("app.tasks.govuk_tasks.dao_cancel_all_pending_publish_tasks")
    created_pending = PublishTaskProgress(id="created-pending")
    mock_create = mocker.patch("app.tasks.govuk_tasks.dao_create_publish_task", return_value=created_pending)
    mock_send = mocker.patch("app.tasks.govuk_tasks._publish_govuk_alerts_full.send", return_value="send")

    create, send = publish_govuk_build_full()

    assert create == created_pending
    assert send == "send"
    mock_delete.assert_called_once()
    mock_create.assert_called_once_with("publish-all", "pending", trace_id=ANY)
    mock_send.assert_called_once_with(pending_progress_id="created-pending")
