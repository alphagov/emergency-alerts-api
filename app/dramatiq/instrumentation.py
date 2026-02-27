import functools
import logging
from typing import Collection

from dramatiq.actor import Actor
from dramatiq_sqs.broker import SQSConsumer, _SQSMessage
from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.trace import SpanKind

logger = logging.getLogger("periodiq")


class SqsBrokerInstrumentor(BaseInstrumentor):
    """
    Instrument the interaction with SQS - namely ensuring message IDs are correctly assigned
    as attributes.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return ["dramatiq >= 1.18.0"]

    def _instrument(self, **kwargs):
        """Instruments the SQS consumer for more detailed trace interaction (IDs)"""

        tracer_provider = kwargs.get("tracer_provider")
        tracer_p = trace.get_tracer_provider()
        tracer = trace.get_tracer(
            __name__,
            "eas-internal",
            tracer_provider=tracer_provider or tracer_p,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        # (We don't instrument __next__ - it gets called an insane amount)

        # ack (delete)
        original_ack = SQSConsumer.ack

        @functools.wraps(original_ack)
        def instrumented_ack(self: SQSConsumer, message: _SQSMessage):

            with tracer.start_as_current_span(
                "dramatiq_sqs.ack",
                kind=SpanKind.INTERNAL,
            ) as span:
                try:
                    span.set_attribute("messaging.message.id", message._sqs_message.message_id)
                except Exception:
                    pass

                return original_ack(self, message)

        SQSConsumer.ack = instrumented_ack

        # send_with_options (Actor)
        # ...the Dramatiq instrumentation starts a trace to inject the context into the message
        # but doesn't actually trace the message send call (either the actor or the broker enqueue)
        # This makes actor calling two unrelated spans - one making the message, the other
        # from sending to SQS. This is hard to see when something like sending a broadcast message
        # creates multiple invocations. So let's have a parent span on the actor's send:
        original_actor_send_with_options = Actor.send_with_options

        @functools.wraps(original_actor_send_with_options)
        def instrumented_actor_send_with_options(self, *, args=(), kwargs=None, delay=None, **options):
            with tracer.start_as_current_span(
                f"dramatiq.actor.{self.actor_name}.send",
                kind=SpanKind.INTERNAL,
            ) as span:
                span.set_attribute("dramatiq.actor.args", str(args))
                span.set_attribute("dramatiq.actor.kwargs", str(kwargs))

                return original_actor_send_with_options(self, args=args, kwargs=kwargs, delay=delay, **options)

        Actor.send_with_options = instrumented_actor_send_with_options

    def _uninstrument(self, **kwargs):
        ack = SQSConsumer.__next__
        if hasattr(ack, "__wrapped__"):
            SQSConsumer.__next__ = ack.__wrapped__

        actor_send_with_options = Actor.send_with_options
        if hasattr(actor_send_with_options, "__wrapped__"):
            Actor.send_with_options = actor_send_with_options.__wrapped__
