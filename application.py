##!/usr/bin/env python

from opentelemetry.instrumentation.auto_instrumentation.sitecustomize import (
    initialize,
)

import app
from app.notify_api_flask_app import NotifyApiFlaskApp

initialize()  # performs the same auto-instrumentation as the CLI
application = NotifyApiFlaskApp("app")
app.create_app(application)
