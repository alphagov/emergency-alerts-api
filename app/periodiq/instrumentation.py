import functools
import logging
from typing import Collection

import periodiq
from dramatiq import Actor
from opentelemetry import trace
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor
from opentelemetry.trace import SpanKind
from pendulum import DateTime

logger = logging.getLogger("periodiq")


class PeriodiqInstrumentor(BaseInstrumentor):
    """
    An instrumentor for Periodiq that starts a span whenever a periodic task is sent.
    """

    def instrumentation_dependencies(self) -> Collection[str]:
        return ["periodiq >= 0.13.0"]

    def _instrument(self, **kwargs):
        """Instruments the dramatiq actors and workers"""

        tracer_provider = kwargs.get("tracer_provider")
        tracer_p = trace.get_tracer_provider()
        tracer = trace.get_tracer(
            __name__,
            "0.0.1-internal",
            tracer_provider=tracer_provider or tracer_p,
            schema_url="https://opentelemetry.io/schemas/1.11.0",
        )

        original_scheduler_send_actors = periodiq.Scheduler.send_actors

        @functools.wraps(original_scheduler_send_actors)
        def instrumented_scheduler_send_actors(self: periodiq.Scheduler, actors: list[Actor], now: DateTime):
            # Unfortunately this loops all due tasks, so we can't just wrap it and instead have to
            # implement the loop ourselves and not call the wrapped method at all.
            now_str = str(now)

            for actor in actors:
                with tracer.start_as_current_span(
                    f"periodiq.producer.{actor.actor_name}",
                    kind=SpanKind.SERVER,
                ) as span:
                    span.set_attribute("eas.cron.schedule", str(actor.options.get("periodic")))

                    logger.info("Scheduling %s at %s.", actor, now_str)
                    actor.send_with_options(scheduled_at=now_str)

        periodiq.Scheduler.send_actors = instrumented_scheduler_send_actors

    def _uninstrument(self, **kwargs):
        func_scheduler_send_actors = periodiq.Scheduler.send_actors
        if hasattr(func_scheduler_send_actors, "__wrapped__"):
            periodiq.Scheduler.send_actors = func_scheduler_send_actors.__wrapped__
