#!/usr/bin/env python

# notify_celery must be imported here
import logging

from app import create_app, notify_celery  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("delivery")
create_app(application)
application.app_context().push()

logger = logging.getLogger(__name__)
logger.info("run_celery init")
