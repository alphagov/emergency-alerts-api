# isort: skip_file
# Called by the Dramatiq CLI as an importable module for workers/periodiq

# Get a created init-ed Flask app
from application import app

# Import so that the decorators run and register the tasks
import app.tasks.broadcast_message_tasks  # noqa
import app.tasks.scheduled_tasks  # noqa

# By importing app we will have init-ed the flask_dramatiq package
# ...and then we can steal its broker here to present to the worker process.
broker = app.dramatiq.broker
