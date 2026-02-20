# Called by the Dramatiq CLI as an importable module for workers

# Get a created init-ed Flask app
from application import app

# By importing we should init the flask_dramatiq package and set the broker on it
# ...and then steal it here to present to the worker process.
broker = app.dramatiq.broker
