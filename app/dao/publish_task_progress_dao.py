from datetime import datetime, timedelta, timezone

from flask import current_app

from app import db
from app.models import (
    PUBLISH_PROGRESS_CANCELLED,
    PUBLISH_PROGRESS_FINISHED,
    PUBLISH_PROGRESS_IN_PROGRESS,
    PUBLISH_PROGRESS_PENDING,
    PublishTaskProgress,
)


def dao_create_publish_task(task_id: str, status: str = None, trace_id: str = None) -> PublishTaskProgress:
    data = PublishTaskProgress(task_id=task_id, status=status, trace_id=trace_id)
    db.session.add(data)
    db.session.commit()
    return PublishTaskProgress.query.filter_by(task_id=task_id).first()


def dao_get_all_pending_publish_tasks() -> list[PublishTaskProgress]:
    return PublishTaskProgress.query.filter_by(status=PUBLISH_PROGRESS_PENDING).all()


def dao_cancel_all_pending_publish_tasks() -> list[PublishTaskProgress]:
    return PublishTaskProgress.query.filter_by(status=PUBLISH_PROGRESS_PENDING).update(
        {
            PublishTaskProgress.finished_at: datetime.now(timezone.utc),
            PublishTaskProgress.status: PUBLISH_PROGRESS_CANCELLED,
        }
    )


def dao_get_all_in_progress_publish_tasks() -> list[PublishTaskProgress]:
    return PublishTaskProgress.query.filter_by(status=PUBLISH_PROGRESS_IN_PROGRESS).all()


def dao_get_all_publish_tasks() -> list[PublishTaskProgress]:
    return PublishTaskProgress.query.all()


def dao_get_all_publish_tasks_older_than(days_older_than: int):
    rows = (
        db.session.query(
            PublishTaskProgress.id,
        )
        .filter(PublishTaskProgress.started_at <= datetime.now() - timedelta(days=days_older_than))
        .all()
    )
    return [str(row[0]) for row in rows]


def dao_get_publish_task(id) -> PublishTaskProgress | None:
    return PublishTaskProgress.query.filter_by(id=id).first()


def dao_update_publish(id, file):
    db.session.query(PublishTaskProgress).filter_by(id=id).update({PublishTaskProgress.last_published_file: file})
    db.session.commit()
    return dao_get_publish_task(id)


def dao_finish_publish(id):
    db.session.query(PublishTaskProgress).filter_by(id=id).update(
        {
            PublishTaskProgress.finished_at: datetime.now(timezone.utc),
            PublishTaskProgress.status: PUBLISH_PROGRESS_FINISHED,
        }
    )
    db.session.commit()
    return dao_get_publish_task(id)


def dao_delete_publish_by_id(id):
    PublishTaskProgress.query.filter_by(id=id).delete()
    db.session.commit()


def dao_purge_old_publish_tasks(days_older_than=1):
    current_app.logger.info(f"Purging publish tasks older than {days_older_than} days")
    publish_task_ids = dao_get_all_publish_tasks_older_than(days_older_than)
    for publish_id in publish_task_ids:
        dao_delete_publish_by_id(publish_id)
    return len(publish_task_ids)  # Returns number of tasks deleted
