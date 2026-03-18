##!/usr/bin/env python

import opentelemetry.instrumentation.auto_instrumentation.sitecustomize  # noqa

import app
from app.dramatiq.instrumentation import DramatiqInstrumentor
from app.notify_api_flask_app import NotifyApiFlaskApp
from app.periodiq.instrumentation import PeriodiqInstrumentor

DramatiqInstrumentor().instrument()
PeriodiqInstrumentor().instrument()

application = NotifyApiFlaskApp("app")
app.create_app(application)
