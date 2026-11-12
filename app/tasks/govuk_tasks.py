from datetime import datetime, timedelta
from uuid import UUID

import pytz
from dramatiq.message import Message
from flask import current_app

from app.dao.publish_task_progress_dao import (
    dao_cancel_all_pending_publish_tasks,
    dao_create_publish_task,
    dao_get_all_pending_publish_tasks,
)
from app.models import PUBLISH_PROGRESS_PENDING, PublishTaskProgress
from app.tasks.stub_tasks import (
    _publish_govuk_alerts,
    _publish_govuk_alerts_full,
)
from app.utils import get_trace_id


def publish_govuk_build(
    broadcast_event_id: UUID = None,
) -> tuple[PublishTaskProgress, Message]:
    """
    Schedule a GovUK publish if no others are pending. Returns the pending model and Dramatiq task if scheduled.
    If one is pending then it's skipped (when the publish runs it'll bring in latest changes anyway) - in such
    a case the first pending model will be returned and None for the Dramatiq task.
    """
    existing_pending = dao_get_all_pending_publish_tasks()

    valid_pending: list[PublishTaskProgress] = []
    too_old_timestamp = (
        datetime.now(pytz.utc) - timedelta(seconds=current_app.config["GOVUK_PENDING_STATUS_MAX_SECONDS"])
    ).timestamp()
    for pending in existing_pending:
        # Make sure not too old...
        if pending.started_at.timestamp() > too_old_timestamp:
            valid_pending.append(pending)
        else:
            current_app.logger.warning(
                "A pending still exists but it's very old? Ignoring it. ID: %s, started at: %s",
                pending.id,
                pending.started_at,
            )

    if len(valid_pending) > 0:
        # There's already a pending publish. Thus scheduling again will not help.
        return existing_pending[0], None

    # The task ID here is a bit arbitrary, but contains the publish type for the out-of-app monitoring
    new_pending = dao_create_publish_task("publish-dynamic", PUBLISH_PROGRESS_PENDING, trace_id=get_trace_id())
    dramatiq_task = _publish_govuk_alerts.send(
        pending_progress_id=str(new_pending.id), broadcast_event_id=broadcast_event_id
    )

    return new_pending, dramatiq_task


def publish_govuk_build_full() -> tuple[PublishTaskProgress, Message]:
    """
    Schedule a 'full' publish (generates every page rather than recent). This will cancel any pending publishes as
    we don't know whether they're partial or full, and full takes precedence.
    """
    dao_cancel_all_pending_publish_tasks()

    # The task ID here is a bit arbitrary, but contains the publish type for the out-of-app monitoring
    new_pending = dao_create_publish_task("publish-all", PUBLISH_PROGRESS_PENDING, trace_id=get_trace_id())
    dramatiq_task = _publish_govuk_alerts_full.send(pending_progress_id=str(new_pending.id))

    return new_pending, dramatiq_task
