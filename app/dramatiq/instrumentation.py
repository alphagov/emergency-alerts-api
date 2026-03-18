import functools
import logging
from typing import Collection

from dramatiq.actor import Actor
from dramatiq.worker import _WorkerThread
from dramatiq_sqs.broker import SQSConsumer, _SQSMessage
from opentelemetry import context, trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind, StatusCode, Tracer

logger = logging.getLogger("dramatiq")


class DramatiqInstrumentor(BaseInstrumentor):
    """
    Instrument the interaction with SQS - namely ensuring message IDs are correctly assigned
    as attributes.
    """

    tracer: Tracer

    def instrumentation_dependencies(self) -> Collection[str]:
        return ["dramatiq >= 1.18.0"]

    def _instrument(self, **kwargs):
        tracer_provider = kwargs.get("tracer_provider")
        tracer_p = trace.get_tracer_provider()

        self.tracer = trace.get_tracer(
            __name__,
            "eas-internal",
            tracer_provider=tracer_provider or tracer_p,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        self.instrument_consumer_ack()
        self.instrument_send_with_options()
        self.instrument_message_with_options()
        self.instrument_worker_process_message()

    def instrument_consumer_ack(self):
        original_ack = SQSConsumer.ack

        @functools.wraps(original_ack)
        def instrumented_ack(consumer_self: SQSConsumer, message: _SQSMessage):

            with self.tracer.start_as_current_span(
                "dramatiq_sqs.ack",
            ) as span:
                try:
                    span.set_attribute("messaging.message.id", message._sqs_message.message_id)
                except Exception:
                    pass

                return original_ack(consumer_self, message)

        SQSConsumer.ack = instrumented_ack

    def instrument_send_with_options(self):
        original_actor_send_with_options = Actor.send_with_options

        @functools.wraps(original_actor_send_with_options)
        def instrumented_actor_send_with_options(actor_self, *, args=(), kwargs=None, delay=None, **options):
            with self.tracer.start_as_current_span(
                f"dramatiq.actor.{actor_self.actor_name}.send_with_options",
            ) as span:
                span.set_attribute("dramatiq.actor.args", str(args))
                span.set_attribute("dramatiq.actor.kwargs", str(kwargs))

                return original_actor_send_with_options(actor_self, args=args, kwargs=kwargs, delay=delay, **options)

        Actor.send_with_options = instrumented_actor_send_with_options

    def instrument_message_with_options(self):
        # Called on creation of a Dramatiq message object, so we can inject the trace context in
        original_message_with_options = Actor.message_with_options

        @functools.wraps(original_message_with_options)
        def instrumented_message_with_options(actor_self, *, args=(), kwargs=None, **options):
            with self.tracer.start_as_current_span(
                f"dramatiq.actor.{actor_self.actor_name}.message_with_options",
                kind=SpanKind.SERVER,
            ) as span:
                span.set_attribute("dramatiq.actor.name", actor_self.actor_name)
                span.set_attribute("dramatiq.actor.queue_name", actor_self.queue_name)

                context_carrier = {}
                inject(context_carrier)

                try:
                    result = original_message_with_options(
                        actor_self,
                        args=args,
                        kwargs=kwargs,
                        options={
                            **options,
                            "trace_context": context_carrier,
                        },
                    )
                except Exception as e:
                    span.set_status(StatusCode.ERROR)
                    span.record_exception(e)
                    raise e
                else:
                    span.set_attribute("dramatiq.message_id", result.message_id)
                    span.set_status(StatusCode.OK)
                    return result

        Actor.message_with_options = instrumented_message_with_options

    def instrument_worker_process_message(self):
        original_process_message = _WorkerThread.process_message

        @functools.wraps(original_process_message)
        def instrumented_process_message(thread_self, message):
            span_name = f"dramatiq.worker.{message.actor_name}.process_message"

            options = message.options.get("options")
            message_trace_context = options.get("trace_context") if options else None

            trace_context = extract(message_trace_context) or None

            with self.tracer.start_as_current_span(
                span_name,
                kind=SpanKind.CLIENT,
                context=trace_context,
            ) as span:
                span.set_attribute("dramatiq.message_id", message.message_id)
                try:
                    result = original_process_message(thread_self, message)
                except Exception as e:
                    span.set_status(StatusCode.ERROR)
                    span.record_exception(e)
                    raise e
                else:
                    span.set_status(StatusCode.OK)
                    return result

        _WorkerThread.process_message = instrumented_process_message

    def _uninstrument(self, **kwargs):
        ack = SQSConsumer.__next__
        if hasattr(ack, "__wrapped__"):
            SQSConsumer.__next__ = ack.__wrapped__

        actor_send_with_options = Actor.send_with_options
        if hasattr(actor_send_with_options, "__wrapped__"):
            Actor.send_with_options = actor_send_with_options.__wrapped__
