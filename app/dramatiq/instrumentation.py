import functools
import logging
from typing import Collection

from dramatiq_sqs.broker import SQSConsumer, _SQSMessage
from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.trace import SpanKind

logger = logging.getLogger("periodiq")


class SqsBrokerInstrumentor(BaseInstrumentor):
    """
    Instrument the interaction with SQS - namely ensuring message IDs are correctly
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return ["periodiq >= 0.13.0"]

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

        # iterator (receieve_messages)
        original_consumer_iterator = SQSConsumer.__next__

        @functools.wraps(original_consumer_iterator)
        def instrumented_consumer_iterator(self: SQSConsumer):
            queue_name = self.queue.url.split("/")[-1]

            # Unfortunately this captures the message being received from SQS, but within the message
            # is a trace context which will be used when dramatiq starts processing the message
            # ...which means this span doesn't get linked into the 'bigger picture' trace of send
            # message -> (receive message) -> do stuff -> delete message.

            # We'd probably need to hack on the Dramatiq instrumentation to embed the trace context here
            # into the _SQSMessage object and then get that to add a link(?) when it resets the trace
            # context to that embedded in the message originally.

            with tracer.start_as_current_span(
                f"dramatiq_sqs.__next__: {queue_name}",
                kind=SpanKind.CONSUMER,
                # Ensure we're a root trace for this
                context=trace.set_span_in_context(trace.INVALID_SPAN),
            ):
                future_message: _SQSMessage = original_consumer_iterator(self)

                if future_message is not None:
                    try:
                        with tracer.start_as_current_span(
                            "SQS.ReceiveMessage: Result",
                            kind=SpanKind.CONSUMER,
                        ) as span:
                            # The Dramatiq instrumentation uses the term message_id for Dramatiq's own message IDs
                            span.set_attribute("message_id", future_message.message_id)

                            sqs_message_id = future_message._sqs_message.message_id
                            span.set_attribute("messaging.message.id", sqs_message_id)
                    except Exception:
                        pass

                return future_message

        SQSConsumer.__next__ = instrumented_consumer_iterator

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

    def _uninstrument(self, **kwargs):
        original_consumer_iterator = SQSConsumer.__next__
        if hasattr(original_consumer_iterator, "__wrapped__"):
            SQSConsumer.__next__ = original_consumer_iterator.__wrapped__

        original_ack = SQSConsumer.__next__
        if hasattr(original_ack, "__wrapped__"):
            SQSConsumer.__next__ = original_ack.__wrapped__
