##!/usr/bin/env python
import os
from app import create_app
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("app")
create_app(application)
