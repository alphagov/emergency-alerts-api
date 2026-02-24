##!/usr/bin/env python

import opentelemetry.instrumentation.auto_instrumentation.sitecustomize  # noqa
from opentelemetry_instrumentor_dramatiq import DramatiqInstrumentor

import app
from app.dramatiq.instrumentation import PeriodiqInstrumentor
from app.notify_api_flask_app import NotifyApiFlaskApp

DramatiqInstrumentor().instrument()
PeriodiqInstrumentor().instrument()

application = NotifyApiFlaskApp("app")
app.create_app(application)
