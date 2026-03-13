from time import time

from flask import Blueprint, jsonify, request

from app.dao.publish_task_progress_dao import (
    dao_create_publish_task,
    dao_finish_publish,
    dao_get_all_in_progress_publish_tasks,
    dao_get_publish_task,
    dao_purge_old_publish_tasks,
    dao_update_publish,
)
from app.errors import register_errors

publish_task_progress_blueprint = Blueprint(
    "publish_task_progress",
    __name__,
    url_prefix="/publish_task_progress",
)

register_errors(publish_task_progress_blueprint)


@publish_task_progress_blueprint.route("add-publish", methods=["POST"])
def add_publish_task():
    task_id = request.get_json().get("task_id")
    task = dao_create_publish_task(task_id)
    return jsonify(task.serialize())


@publish_task_progress_blueprint.route("/update-publish", methods=["POST"])
def update_publish_task():
    data = request.get_json()
    task_id = data.get("task_id")
    file = data.get("file")
    task = dao_update_publish(task_id, file)
    return jsonify(task.serialize())


@publish_task_progress_blueprint.route("/get-publish", methods=["POST"])
def get_publish_progress():
    data = request.get_json()
    task_id = data.get("task_id")
    task = dao_get_publish_task(task_id)
    return jsonify(task.serialize())


@publish_task_progress_blueprint.route("/finish-publish", methods=["POST"])
def finish_publish():
    data = request.get_json()
    task_id = data.get("task_id")
    task = dao_finish_publish(task_id)
    return jsonify(task.serialize())


@publish_task_progress_blueprint.route("/get-publish-tasks", methods=["GET"])
def get_publish_tasks():
    now = time()
    tasks = dao_get_all_in_progress_publish_tasks()

    result = {
        "failed": {"publish-all": [], "publish-dynamic": []},
        "ongoing": {"publish-all": [], "publish-dynamic": []},
    }

    for task in tasks:
        status = "failed" if has_publish_failed(now, task) else "ongoing"
        task_data = parse_task_id(task.id)
        publish_type = task_data.get("publish_type")

        if publish_type not in result[status]:
            continue

        result[status][publish_type].append(task.id)

    return jsonify(result)


def parse_task_id(task_id):
    publish_type, publish_origin, timestamp = task_id.split("_")
    return {"publish_type": publish_type, "publish_origin": publish_origin, "timestamp": timestamp}


def has_publish_failed(now, task, failed_publish_interval=5.0):
    if task.last_activity_at:
        return now - task.last_activity_at.timestamp() > failed_publish_interval
    else:
        # If `last_activity_at` hasn't been set, the publish may have started and
        # no activity yet, so we check `started_at` timestamp
        return now - task.started_at.timestamp() > failed_publish_interval


@publish_task_progress_blueprint.route("/purge/<int:older_than>", methods=["DELETE"])
def purge_publish_tasks(days_older_than):
    try:
        count = dao_purge_old_publish_tasks(days_older_than)
    except Exception:
        return jsonify(result="error", message="Unable to purge old publish tasks"), 500

    return (
        jsonify({"message": f"Purged {count} publish tasks created more than {days_older_than} days ago"}),
        200,
    )
