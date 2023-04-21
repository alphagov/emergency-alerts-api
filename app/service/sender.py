from flask import current_app

from app.clients.notify_client import get_notify_template, notify_send
from app.dao.services_dao import dao_fetch_active_users_for_service
from app.dao.templates_dao import dao_get_template_by_id
from app.models import EMAIL_TYPE


def send_notification_to_service_users(service_id, template_id, personalisation=None, include_user_fields=None):
    personalisation = personalisation or {}
    include_user_fields = include_user_fields or []

    template = dao_get_template_by_id(template_id)
    active_users = dao_fetch_active_users_for_service(service_id)

    for user in active_users:
        personalisation = _add_user_fields(user, personalisation, include_user_fields)
        template = get_notify_template(template_id)

        notification = {
            "type": template.type,
            "template_id": current_app.config["PASSWORD_RESET_TEMPLATE_ID"],
            "personalisation": personalisation,
            "recipient": user.email_address if template.type == EMAIL_TYPE else user.mobile_number,
            "reply_to": current_app.config["EAS_EMAIL_REPLY_TO_ID"] if template.type == EMAIL_TYPE else None,
        }

        notify_send(notification)


def _add_user_fields(user, personalisation, fields):
    for field in fields:
        personalisation[field] = getattr(user, field)
    return personalisation
