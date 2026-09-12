from datetime import datetime, timedelta, timezone

from flask import current_app

from app import db
from app.models import PublishTaskProgress


def dao_create_publish_task(task_id):
    data = PublishTaskProgress(task_id=task_id)
    db.session.add(data)
    db.session.commit()
    return PublishTaskProgress.query.filter_by(task_id=task_id).first()


def dao_get_all_in_progress_publish_tasks():
    return PublishTaskProgress.query.filter_by(finished_at=None).all()


def dao_get_live_in_progress_publish_tasks(stale_after_seconds):
    """
    In-progress publish tasks (finished_at IS NULL) that are still 'live',
    i.e., that have shown activity within stale_after_seconds.
    Tasks that have gone quiet for longer are deliberately excluded.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=stale_after_seconds)
    return PublishTaskProgress.query.filter(
        PublishTaskProgress.finished_at.is_(None),
        PublishTaskProgress.last_activity_at >= cutoff,
    ).all()


def dao_get_publish_tasks_finished_within(within_seconds):
    """
    Publish tasks that finished within the last within_seconds.
    """
    cutoff = datetime.utcnow() - timedelta(seconds=within_seconds)
    return PublishTaskProgress.query.filter(
        PublishTaskProgress.finished_at.isnot(None),
        PublishTaskProgress.finished_at >= cutoff,
    ).all()


def dao_get_all_publish_tasks():
    return PublishTaskProgress.query.all()


def dao_get_all_publish_tasks_older_than(days_older_than):
    rows = (
        db.session.query(
            PublishTaskProgress.id,
        )
        .filter(PublishTaskProgress.started_at <= datetime.now() - timedelta(days=days_older_than))
        .all()
    )
    return [str(row[0]) for row in rows]


def dao_get_publish_task(id):
    return PublishTaskProgress.query.filter_by(id=id).first()


def dao_update_publish(id, file):
    db.session.query(PublishTaskProgress).filter_by(id=id).update({PublishTaskProgress.last_published_file: file})
    db.session.commit()
    return dao_get_publish_task(id)


def dao_finish_publish(id):
    db.session.query(PublishTaskProgress).filter_by(id=id).update(
        {PublishTaskProgress.finished_at: datetime.now(timezone.utc)}
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
