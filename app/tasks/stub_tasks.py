from emergency_alerts_utils.tasks import QueueNames, TaskNames
from periodiq import cron

from app import dramatiq

# These are 'stub tasks' - ones not actually executed here, but the function is decorated so that
# dramatiq can bind an actor name and queue name in this repo.


@dramatiq.actor(actor_name=TaskNames.PUBLISH_GOVUK_ALERTS_FULL, queue_name=QueueNames.GOVUK_ALERTS)
def _publish_govuk_alerts_full(*args, **kwargs):
    """
    Note: You likely want to look at govuk_tasks instead, as it has logic to avoid scheduling multiple runs
    """
    return _not_implemented(TaskNames.PUBLISH_GOVUK_ALERTS_FULL)


@dramatiq.actor(actor_name=TaskNames.PUBLISH_GOVUK_ALERTS, queue_name=QueueNames.GOVUK_ALERTS)
def _publish_govuk_alerts(*args, **kwargs):
    """
    Note: You likely want to look at govuk_tasks instead, as it has logic to avoid scheduling multiple runs
    """
    return _not_implemented(TaskNames.PUBLISH_GOVUK_ALERTS)


@dramatiq.actor(
    actor_name=TaskNames.TRIGGER_GOVUK_HEALTHCHECK, queue_name=QueueNames.GOVUK_ALERTS, periodic=cron("*/1 * * * *")
)
def trigger_govuk_healthcheck(*args, **kwargs):
    return _not_implemented(TaskNames.TRIGGER_GOVUK_HEALTHCHECK)


def _not_implemented(task_name: str):
    raise NotImplementedError(
        f"Attempted to run {task_name} but this is the "
        "API worker - not govuk. Either this task was sent on the wrong queue or we're consuming the wrong queue."
    )
