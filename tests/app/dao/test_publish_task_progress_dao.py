from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.dao.publish_task_progress_dao import (
    dao_cancel_all_pending_publish_tasks,
    dao_create_publish_task,
    dao_delete_publish_by_id,
    dao_finish_publish,
    dao_get_all_pending_or_in_progress_publish_tasks,
    dao_get_all_pending_publish_tasks,
    dao_get_all_publish_tasks,
    dao_get_all_publish_tasks_older_than,
    dao_get_publish_task,
    dao_purge_old_publish_tasks,
    dao_update_publish,
)
from app.models import (
    PUBLISH_PROGRESS_CANCELLED,
    PUBLISH_PROGRESS_FINISHED,
    PUBLISH_PROGRESS_PENDING,
    PublishTaskProgress,
)


@pytest.mark.parametrize(
    "status, expected_status",
    [
        [
            None,  # Default
            "in_progress",
        ],
        [
            PUBLISH_PROGRESS_PENDING,
            "pending",
        ],
    ],
)
def test_dao_create_publish_task(notify_db_session, status, expected_status):
    task_id = "test-task-id"
    result = dao_create_publish_task(task_id, status=status, trace_id="test")

    assert result.task_id == task_id
    assert result.status == expected_status
    assert result.trace_id == "test"
    assert PublishTaskProgress.query.filter_by(task_id=task_id).one() == result


def test_dao_get_all_pending_publish_tasks(notify_db_session):
    task1 = PublishTaskProgress(task_id="test-task1", finished_at=None)
    task2 = PublishTaskProgress(task_id="test-task2", finished_at=None)
    task3 = PublishTaskProgress(
        task_id="test-task3-finished", status=PUBLISH_PROGRESS_FINISHED, finished_at=datetime.now(timezone.utc)
    )
    task4 = PublishTaskProgress(task_id="test-task4-pending", status=PUBLISH_PROGRESS_PENDING)
    db.session.add_all([task1, task2, task3, task4])
    db.session.commit()

    results = {task.task_id for task in dao_get_all_pending_publish_tasks()}
    assert results == {task4.task_id}


def test_dao_cancel_all_pending_publish_tasks(notify_db_session):
    task1 = PublishTaskProgress(task_id="test-task1", finished_at=None)
    task2 = PublishTaskProgress(task_id="test-task2", finished_at=None)
    task3 = PublishTaskProgress(
        task_id="test-task3-finished", status=PUBLISH_PROGRESS_FINISHED, finished_at=datetime.now(timezone.utc)
    )
    task4 = PublishTaskProgress(task_id="test-task4-pending", status=PUBLISH_PROGRESS_PENDING)
    db.session.add_all([task1, task2, task3, task4])
    db.session.commit()

    dao_cancel_all_pending_publish_tasks()
    assert len(dao_get_all_pending_publish_tasks()) == 0
    assert PublishTaskProgress.query.filter_by(task_id=task4.task_id).first().status == PUBLISH_PROGRESS_CANCELLED


def test_dao_get_all_pending_or_in_progress_publish_tasks(notify_db_session):
    task1 = PublishTaskProgress(task_id="test-task1", finished_at=None)
    task2 = PublishTaskProgress(task_id="test-task2", finished_at=None)
    task3 = PublishTaskProgress(
        task_id="test-task3-finished", status=PUBLISH_PROGRESS_FINISHED, finished_at=datetime.now(timezone.utc)
    )
    task4 = PublishTaskProgress(task_id="test-task4-pending", status=PUBLISH_PROGRESS_PENDING)
    db.session.add_all([task1, task2, task3, task4])
    db.session.commit()

    results = {task.task_id for task in dao_get_all_pending_or_in_progress_publish_tasks()}
    assert results == {task1.task_id, task2.task_id, task4.task_id}


def test_dao_get_all_publish_tasks_older_than(notify_db_session):
    old = PublishTaskProgress(task_id="old", started_at=datetime(2020, 12, 22))
    recent = PublishTaskProgress(task_id="recent", started_at=datetime.now(timezone.utc))
    db.session.add_all([old, recent])
    db.session.commit()

    ids = dao_get_all_publish_tasks_older_than(2)

    assert ids == [str(old.id)]


def test_dao_get_publish_task(notify_db_session):
    publish_task = PublishTaskProgress(task_id="test-task-id")
    db.session.add(publish_task)
    db.session.commit()

    result = dao_get_publish_task(publish_task.id)

    assert result.id == publish_task.id
    assert result.task_id == "test-task-id"


def test_dao_update_publish(notify_db_session):
    publish_task = PublishTaskProgress(task_id="task-id-update", last_published_file=None)
    db.session.add(publish_task)
    db.session.commit()

    result = dao_update_publish(publish_task.id, "file.txt")

    assert result.last_published_file == "file.txt"
    assert PublishTaskProgress.query.get(publish_task.id).last_published_file == "file.txt"


def test_dao_finish_publish(notify_db_session):
    publish_task = PublishTaskProgress(task_id="test-task-id", finished_at=None)
    db.session.add(publish_task)
    db.session.commit()

    before = datetime.now(timezone.utc)
    result = dao_finish_publish(publish_task.id)
    after = datetime.now(timezone.utc)

    assert result.finished_at is not None
    # Add TZ for comparison with other timestamps
    finished_at = result.finished_at.replace(tzinfo=timezone.utc)
    assert before <= finished_at <= after
    assert result.status == PUBLISH_PROGRESS_FINISHED


def test_dao_delete_publish_by_id(notify_db_session):
    publish_task = PublishTaskProgress(task_id="task-id")
    db.session.add(publish_task)
    db.session.commit()

    dao_delete_publish_by_id(publish_task.id)

    assert PublishTaskProgress.query.get(publish_task.id) is None


def test_dao_purge_old_publish_tasks(notify_db_session):
    past_date = datetime(2024, 12, 22)

    old1 = PublishTaskProgress(task_id="old-task-1", started_at=past_date - timedelta(days=3))
    old2 = PublishTaskProgress(task_id="old-task-2", started_at=past_date - timedelta(days=4))
    recent = PublishTaskProgress(task_id="recent-task", started_at=datetime.now(timezone.utc) - timedelta(hours=6))
    db.session.add_all([old1, old2, recent])
    db.session.commit()

    all_tasks = dao_get_all_publish_tasks()
    assert len(all_tasks) == 3

    count = dao_purge_old_publish_tasks(days_older_than=2)

    assert count == 2  # 2 have been deleted
    all_tasks = dao_get_all_publish_tasks()
    assert len(all_tasks) == 1  # Confirms that 2 have been deleted
