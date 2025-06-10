#!/usr/bin/env python

import os

# notify_celery must be imported here
from app import create_app, notify_celery  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("delivery")
create_app(application)

service_name = os.environ.get("SERVICE", "unknown")
application.logger.info(
    f"{service_name.upper()} DELIVERY Database configuration",
    extra={
        "python_module": __name__,
        "sqlalchemy_engine_options": application.config["SQLALCHEMY_ENGINE_OPTIONS"],
        "database_statement_timeout_ms": application.config["DATABASE_STATEMENT_TIMEOUT_MS"],
        "sqlalchemy_database_uri": application.config["SQLALCHEMY_DATABASE_URI"],
    },
)

application.app_context().push()
