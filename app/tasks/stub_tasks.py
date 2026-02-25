from datetime import timedelta
from typing import Any, Optional

from dramatiq.message import Message
from emergency_alerts_utils.tasks import QueueNames, TaskNames

from app import dramatiq


class _SendOnlyActor:
    # Similar to an Actor, but isn't one.
    # The reason is the @actor decorator from flask_dramatiq will lazily instantiate an Actor
    # instance via the broker's register_actor method, which will always use the Actor class.
    # This class' init method will register itself to the broker, at which point the broker will
    # then listen out for the queue - not what we want.

    # Rather than monkeypatch this behaviour awkwardly, it's tideier just to create a convenience
    # method for sending since it's only this file.

    def __init__(self, actor_name: str, queue_name: str):
        self.actor_name = actor_name
        self.queue_name = queue_name

    def message_with_options(
        self,
        *,
        args: tuple = (),
        kwargs: Optional[dict[str, Any]] = None,
        **options,
    ) -> Message:
        return Message(
            queue_name=self.queue_name,
            actor_name=self.actor_name,
            args=args,
            kwargs=kwargs or {},
            options=options,
        )

    def send(self, *args, **kwargs) -> Message:
        return self.send_with_options(args=args, kwargs=kwargs)

    def send_with_options(
        self,
        *,
        args: tuple = (),
        kwargs: Optional[dict[str, Any]] = None,
        delay: int = None,
        **options,
    ) -> Message:
        """Asynchronously send a message to this actor, along with an
        arbitrary set of processing options for the broker and
        middleware.

        Parameters:
          args(tuple): Positional arguments that are passed to the actor.
          kwargs(dict): Keyword arguments that are passed to the actor.
          delay(int): The minimum amount of time, in milliseconds, the
            message should be delayed by. Also accepts a timedelta.
          **options: Arbitrary options that are passed to the
            broker and any registered middleware.

        Returns:
          Message: The enqueued message.
        """
        if isinstance(delay, timedelta):
            delay = int(delay.total_seconds() * 1000)

        message = self.message_with_options(args=args, kwargs=kwargs, **options)
        return dramatiq.broker.enqueue(message, delay=delay)


publish_govuk_alerts = _SendOnlyActor(actor_name=TaskNames.PUBLISH_GOVUK_ALERTS, queue_name=QueueNames.GOVUK_ALERTS)

# TODO: Scheduled - but it's not an actor...
trigger_govuk_healthcheck = _SendOnlyActor(
    actor_name=TaskNames.TRIGGER_GOVUK_HEALTHCHECK, queue_name=QueueNames.GOVUK_ALERTS
)
