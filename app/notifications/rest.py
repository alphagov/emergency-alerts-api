from emergency_alerts_utils import SMS_CHAR_COUNT_LIMIT
from flask import Blueprint, current_app, jsonify, request

from app import api_user, authenticated_service

from app.dao import notifications_dao
from app.errors import InvalidRequest, register_errors
from app.models import KEY_TYPE_TEAM, SMS_TYPE

from app.schemas import (
    notification_with_personalisation_schema,
    notifications_filter_schema,
)
from app.service.utils import service_allowed_to_send_to
from app.utils import pagination_links

notifications = Blueprint("notifications", __name__)

register_errors(notifications)


@notifications.route("/notifications/<uuid:notification_id>", methods=["GET"])
def get_notification_by_id(notification_id):
    notification = notifications_dao.get_notification_with_personalisation(
        str(authenticated_service.id), notification_id, key_type=None
    )
    return jsonify(data={"notification": notification_with_personalisation_schema.dump(notification)}), 200


@notifications.route("/notifications", methods=["GET"])
def get_all_notifications():
    data = notifications_filter_schema.load(request.args)

    include_jobs = data.get("include_jobs", False)
    page = data.get("page", 1)
    page_size = data.get("page_size", current_app.config.get("API_PAGE_SIZE"))
    limit_days = data.get("limit_days")

    pagination = notifications_dao.get_notifications_for_service(
        str(authenticated_service.id),
        personalisation=True,
        filter_dict=data,
        page=page,
        page_size=page_size,
        limit_days=limit_days,
        key_type=api_user.key_type,
        include_jobs=include_jobs,
    )
    return (
        jsonify(
            notifications=notification_with_personalisation_schema.dump(pagination.items, many=True),
            page_size=page_size,
            total=pagination.total,
            links=pagination_links(pagination, ".get_all_notifications", **request.args.to_dict()),
        ),
        200,
    )


def get_notification_return_data(notification_id, notification, template):
    output = {
        "template_version": notification["template_version"],
        "notification": {"id": notification_id},
        "body": template.content_with_placeholders_filled_in,
    }

    if hasattr(template, "subject"):
        output["subject"] = template.subject

    return output


def create_template_object_for_notification(template, personalisation):
    template_object = template._as_utils_template_with_personalisation(personalisation)

    if template_object.missing_data:
        message = "Missing personalisation: {}".format(", ".join(template_object.missing_data))
        errors = {"template": [message]}
        raise InvalidRequest(errors, status_code=400)

    if template_object.template_type == SMS_TYPE and template_object.is_message_too_long():
        message = "Content has a character count greater than the limit of {}".format(SMS_CHAR_COUNT_LIMIT)
        errors = {"content": [message]}
        raise InvalidRequest(errors, status_code=400)
    return template_object
