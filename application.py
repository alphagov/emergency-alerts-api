##!/usr/bin/env python
import app
from app.notify_api_flask_app import NotifyApiFlaskApp

application = NotifyApiFlaskApp("app")
app.create_app(application)
