from unittest.mock import ANY

from app.models import (
    PublishTaskProgress,
)
from app.tasks.govuk_tasks import publish_govuk_build, publish_govuk_build_full


def test_publish_schedules_when_no_pending_tasks_present(mocker):
    mocker.patch(
        "app.tasks.govuk_tasks.dao_get_all_pending_publish_tasks",
        return_value=[],
    )
    mock_create = mocker.patch("app.tasks.govuk_tasks.dao_create_publish_task", return_value="create")
    mock_send = mocker.patch("app.tasks.govuk_tasks._publish_govuk_alerts.send", return_value="send")

    create, send = publish_govuk_build("test")

    assert create == "create"
    assert send == "send"
    mock_create.assert_called_once_with("test", "pending", trace_id=ANY)
    mock_send.assert_called_once_with(broadcast_event_id="test")


def test_does_not_schedule_when_pending_tasks_present(mocker):
    mocker.patch(
        "app.tasks.govuk_tasks.dao_get_all_pending_publish_tasks",
        return_value=[PublishTaskProgress()],
    )
    mock_create = mocker.patch("app.tasks.govuk_tasks.dao_create_publish_task", return_value="create")
    mock_send = mocker.patch("app.tasks.govuk_tasks._publish_govuk_alerts.send", return_value="send")

    ret = publish_govuk_build()
    assert ret == (None, None)

    mock_create.assert_not_called()
    mock_send.assert_not_called()


def test_full_publish_always_schedules_and_deletes_pending(mocker):
    mock_delete = mocker.patch("app.tasks.govuk_tasks.dao_cancel_all_pending_publish_tasks")
    mock_create = mocker.patch("app.tasks.govuk_tasks.dao_create_publish_task", return_value="create")
    mock_send = mocker.patch("app.tasks.govuk_tasks._publish_govuk_alerts_full.send", return_value="send")

    create, send = publish_govuk_build_full()

    assert create == "create"
    assert send == "send"
    mock_delete.assert_called_once()
    mock_create.assert_called_once_with("api-scheduled-full", "pending", trace_id=ANY)
    mock_send.assert_called_once_with()
