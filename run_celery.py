#!/usr/bin/env python

import os

# notify_celery must be imported here
from app import create_app, notify_celery  # noqa
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("delivery")
create_app(application)
application.app_context().push()
