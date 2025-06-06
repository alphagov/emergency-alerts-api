##!/usr/bin/env python
import os

from __future__ import print_function

from app import create_app
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("app")
create_app(application)

service_name = os.environ.get("SERVICE", "unknown")
application.logger.info(
    f"{service_name.upper()} service Database configuration",
    extra={
        "python_module": __name__,
        "sqlalchemy_engine_options": application.config["SQLALCHEMY_ENGINE_OPTIONS"],
        "database_statement_timeout_ms": application.config["DATABASE_STATEMENT_TIMEOUT_MS"],
        "sqlalchemy_database_uri": application.config["SQLALCHEMY_DATABASE_URI"],
    },
)
