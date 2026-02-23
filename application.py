##!/usr/bin/env python

import opentelemetry.instrumentation.auto_instrumentation.sitecustomize  # noqa

import app
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("app")
app.create_app(application)
