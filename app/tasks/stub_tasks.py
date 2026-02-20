from emergency_alerts_utils.tasks import QueueNames, TaskNames

from app import dramatiq

# These are 'stub tasks' - ones not actually executed here, but the function is decorated so that
# dramatiq can bind an actor name and queue name in this repo.


@dramatiq.actor(actor_name=TaskNames.PUBLISH_GOVUK_ALERTS, queue_name=QueueNames.GOVUK_ALERTS)
def publish_govuk_alerts():
    pass
