from datetime import datetime

from tests.app.db import create_publish_task


def test_add_publish_task(notify_db_session, govuk_publish_request):
    response = govuk_publish_request.post("publish_task_progress.add_publish_task", _data={"task_id": "test"})
    assert response == {
        "id": response["id"],
        "task_id": "test",
        "started_at": response["started_at"],
        "finished_at": None,
        "last_activity_at": response["last_activity_at"],
        "last_published_file": None,
    }


def test_update_publish_task(notify_db_session, govuk_publish_request):
    publish_task = create_publish_task()
    govuk_publish_request.post(
        "publish_task_progress.update_publish_task",
        _data={"id": str(publish_task.id), "file": "test_file.txt"},
    )

    updated_task = govuk_publish_request.post(
        "publish_task_progress.get_publish_progress",
        _data={"id": str(publish_task.id)},
    )
    assert updated_task["id"] == str(publish_task.id)
    assert updated_task["task_id"] == publish_task.task_id
    assert updated_task["last_published_file"] == "test_file.txt"
    assert updated_task["started_at"] is not None
    assert updated_task["last_activity_at"] is not None


def test_get_publish_progress(notify_db_session, govuk_publish_request):
    publish_task = create_publish_task()

    result = govuk_publish_request.post(
        "publish_task_progress.get_publish_progress",
        _data={"id": str(publish_task.id)},
    )

    assert result["id"] == str(publish_task.id)
    assert result["task_id"] == publish_task.task_id
    assert "started_at" in result
    assert "finished_at" in result
    assert "last_activity_at" in result
    assert "last_published_file" in result


def test_finish_publish(notify_db_session, govuk_publish_request):
    publish_task = create_publish_task()
    assert publish_task.finished_at is None

    govuk_publish_request.post(
        "publish_task_progress.finish_publish",
        _data={"id": str(publish_task.id)},
    )

    result = govuk_publish_request.post(
        "publish_task_progress.get_publish_progress",
        _data={"id": str(publish_task.id)},
    )

    assert result["id"] == str(publish_task.id)
    assert result["finished_at"] is not None
    assert result["last_activity_at"] is not None


def test_get_publish_tasks_returns_ongoing_publish_tasks(notify_db_session, govuk_publish_request):
    create_publish_task(task_id="publish-all_origin1_123")
    create_publish_task(task_id="publish-dynamic_origin2_124")

    result = govuk_publish_request.get("publish_task_progress.get_publish_tasks")

    assert "ongoing" in result
    assert "publish-all" in result["ongoing"]
    assert "publish-dynamic" in result["ongoing"]


def test_get_publish_tasks_returns_failed_publish_tasks(notify_db_session, govuk_publish_request):
    create_publish_task(task_id="publish-all_origin1_123")
    create_publish_task(task_id="publish-dynamic_origin2_124", last_activity_at=datetime(2020, 12, 22))

    result = govuk_publish_request.get("publish_task_progress.get_publish_tasks")

    assert "ongoing" in result
    assert "failed" in result
    assert "publish-all" in result["ongoing"]
    assert "publish-dynamic" in result["failed"]


def test_get_publish_tasks_gets_no_tasks(notify_db_session, govuk_publish_request):
    result = govuk_publish_request.get("publish_task_progress.get_publish_tasks")
    assert result == {}


def test_purge_publish_tasks(notify_db_session, govuk_publish_request):
    create_publish_task(task_id="publish-all_origin1_123", started_at=datetime(2020, 12, 22))

    govuk_publish_request.delete(
        "publish_task_progress.purge_publish_tasks",
        days_older_than=1,
        _expected_status=200,
    )

    tasks = govuk_publish_request.get("publish_task_progress.get_publish_tasks")
    assert tasks == {}
