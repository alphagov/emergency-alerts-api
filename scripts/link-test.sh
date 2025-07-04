#! /bin/bash

cd /eas/emergency-alerts-api;
. /venv/emergency-alerts-api/bin/activate;
celery -A run_celery.notify_celery call --queue periodic-tasks trigger-all-link-tests;
