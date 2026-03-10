from datetime import datetime, timezone

from app import db
from app.models import PublishTaskProgress


def dao_create_publish_task(task_id):
    data = PublishTaskProgress(
        id=task_id,
    )
    db.session.add(data)
    db.session.commit()
    return PublishTaskProgress.query.filter_by(id=task_id).first()


def dao_get_all_in_progress_publish_tasks():
    return PublishTaskProgress.query.filter_by(finished_at=None).all()


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
