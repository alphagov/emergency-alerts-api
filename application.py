##!/usr/bin/env python

import opentelemetry.instrumentation.auto_instrumentation.sitecustomize  # noqa
from opentelemetry_instrumentor_dramatiq import DramatiqInstrumentor

import app
from app.notify_api_flask_app import NotifyApiFlaskApp

DramatiqInstrumentor().instrument()

application = NotifyApiFlaskApp("app")
app.create_app(application)
