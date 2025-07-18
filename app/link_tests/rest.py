from emergency_alerts_utils.celery import QueueNames, TaskNames
from flask import Blueprint, request

from app import notify_celery

link_tests = Blueprint("link_tests", __name__)


@link_tests.route("/_trigger_link_tests", methods=["POST"])
def manually_trigger_link_tests():
    data = request.get_json()

    notify_celery.send_task(
        name=TaskNames.TRIGGER_LINK_TEST,
        queue=QueueNames.PERIODIC,
        kwargs=data,
    )

    if "cbc" in data:
        response_message = f"Link tests launched for {data['cbc'].upper()}"
    else:
        response_message = "Link tests launched for all CBCs"

    return (response_message, 200)
