from emergency_alerts_utils.tasks import QueueNames, TaskNames

from app import dramatiq

# These are 'stub tasks' - ones not actually executed here, but the function is decorated so that
# dramatiq can bind an actor name and queue name in this repo.


@dramatiq.actor(actor_name=TaskNames.PUBLISH_GOVUK_ALERTS, queue_name=QueueNames.GOVUK_ALERTS)
def publish_govuk_alerts(*args, **kwargs):
    raise NotImplementedError(
        f"Attempted to run {TaskNames.PUBLISH_GOVUK_ALERTS} but this is the "
        "API worker - not govuk. Either this task was sent on the wrong queue or we're consuming the wrong queue."
    )


@dramatiq.actor(actor_name=TaskNames.TRIGGER_GOVUK_HEALTHCHECK, queue_name=QueueNames.GOVUK_ALERTS)
def trigger_govuk_healthcheck(*args, **kwargs):
    raise NotImplementedError(
        f"Attempted to run {TaskNames.TRIGGER_GOVUK_HEALTHCHECK} but this is the "
        "API worker - not govuk. Either this task was sent on the wrong queue or we're consuming the wrong queue."
    )
