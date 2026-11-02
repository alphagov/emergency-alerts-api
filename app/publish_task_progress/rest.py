from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from app import db
from app.dao.publish_task_progress_dao import (
    dao_create_publish_task,
    dao_finish_publish,
    dao_get_all_in_progress_publish_tasks,
    dao_get_publish_task,
    dao_purge_old_publish_tasks,
    dao_update_publish,
)
from app.errors import register_errors
from app.models import PUBLISH_PROGRESS_IN_PROGRESS

publish_task_progress_blueprint = Blueprint(
    "publish_task_progress",
    __name__,
    url_prefix="/publish_task_progress",
)

register_errors(publish_task_progress_blueprint)

accepted_publish_types = ["publish-all", "publish-dynamic"]
accepted_publish_status = ["failed", "ongoing"]


@publish_task_progress_blueprint.route("/add-publish", methods=["POST"])
def add_publish_task():
    # While we hope the OTel trace context is propagated to this request anyway, let's just let GovUK explicitly state
    # what it thinks the current trace is.
    trace_id = request.get_json().get("trace_id")
    task_id = request.get_json().get("task_id")

    # If we're given an explicit ID (not a task_id, which is just something GovUK generates) then it's something API
    # scheduled earlier and would already have a row.
    # (If not then we just retain backwards compatibility and/or allow ad-hoc publishes via the CLI)
    publish_id = request.get_json().get("id")

    if publish_id is not None:
        task = dao_get_publish_task(publish_id)
        task.status = PUBLISH_PROGRESS_IN_PROGRESS
        task.task_id = task_id
        task.trace_id = trace_id
        db.session.commit()
    else:
        task = dao_create_publish_task(task_id, trace_id=trace_id)

    return jsonify(task.serialize())


@publish_task_progress_blueprint.route("/update-publish", methods=["POST"])
def update_publish_task_file():
    data = request.get_json()
    id = data.get("id")
    file = data.get("file")
    task = dao_update_publish(id, file)
    return jsonify(task.serialize())


@publish_task_progress_blueprint.route("/get-publish", methods=["POST"])
def get_publish_progress():
    data = request.get_json()
    id = data.get("id")
    task = dao_get_publish_task(id)
    return jsonify(task.serialize())


@publish_task_progress_blueprint.route("/finish-publish", methods=["POST"])
def finish_publish():
    data = request.get_json()
    id = data.get("id")
    task = dao_finish_publish(id)
    return jsonify(task.serialize())


@publish_task_progress_blueprint.route("/get-publish-tasks", methods=["GET"])
def get_publish_tasks():
    now = datetime.utcnow().timestamp()
    tasks = dao_get_all_in_progress_publish_tasks()

    result = {}

    for task in tasks:
        status = "failed" if has_publish_failed(now, task) else "ongoing"
        task_data = parse_task_id(task.task_id)
        publish_type = task_data.get("publish_type")

        if (status not in accepted_publish_status) or (publish_type not in accepted_publish_types):
            continue

        # Check if "ongoing" or "failed" keys already in dict, if not add them
        if status not in result:
            result[status] = {}

        # Check if publish_type already in dict, for relevant status
        # If not, add this
        if publish_type not in result[status]:
            result[status][publish_type] = []

        result[status][publish_type].append(task.task_id)
    return jsonify(result)


def parse_task_id(task_id):
    publish_type, publish_origin, timestamp = task_id.split("_")
    return {"publish_type": publish_type, "publish_origin": publish_origin, "timestamp": timestamp}


def has_publish_failed(now, task):
    return now - task.last_activity_at.timestamp() > current_app.config.get("GOVUK_PUBLISH_CHECKS_FAILED_INTERVAL")


@publish_task_progress_blueprint.route("/purge/<int:days_older_than>", methods=["DELETE"])
def purge_publish_tasks(days_older_than=1):
    try:
        count = dao_purge_old_publish_tasks(days_older_than)
    except Exception:
        return jsonify(result="error", message="Unable to purge old publish tasks"), 500

    return (
        jsonify({"message": f"Purged {count} publish tasks created more than {days_older_than} days ago"}),
        200,
    )
