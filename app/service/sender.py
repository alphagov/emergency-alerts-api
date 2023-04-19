from flask import current_app

# from app.notifications.process_notifications import (
#     persist_notification,
#     send_notification_to_queue,
# )
from app.clients.notify_client import get_notify_template, notify_send

# from app.config import QueueNames
from app.dao.services_dao import (  # dao_fetch_service_by_id,
    dao_fetch_active_users_for_service,
)
from app.dao.templates_dao import dao_get_template_by_id
from app.models import EMAIL_TYPE


def send_notification_to_service_users(service_id, template_id, personalisation=None, include_user_fields=None):
    personalisation = personalisation or {}
    include_user_fields = include_user_fields or []

    template = dao_get_template_by_id(template_id)
    # service = dao_fetch_service_by_id(service_id)
    active_users = dao_fetch_active_users_for_service(service_id)
    # notify_service = dao_fetch_service_by_id(current_app.config["NOTIFY_SERVICE_ID"])

    for user in active_users:
        personalisation = _add_user_fields(user, personalisation, include_user_fields)

        # notification = persist_notification(
        #     template_id=template.id,
        #     template_version=template.version,
        #     recipient=user.email_address if template.template_type == EMAIL_TYPE else user.mobile_number,
        #     service=notify_service,
        #     personalisation=personalisation,
        #     notification_type=template.template_type,
        #     api_key_id=None,
        #     key_type=KEY_TYPE_NORMAL,
        #     reply_to_text=notify_service.get_default_reply_to_email_address(),
        # )
        # send_notification_to_queue(notification, False, queue=QueueNames.NOTIFY)

        template = get_notify_template(template_id)
        # notification = {}
        # notification["type"] = template.type
        # notification["template_id"] = current_app.config["PASSWORD_RESET_TEMPLATE_ID"]
        # notification["personalisation"] = personalisation
        # if template.type == EMAIL_TYPE:
        #     notification["reply_to"] = current_app.config["EAS_EMAIL_REPLY_TO_ID"]
        #     notification["recipient"] = user.email_address
        # else:
        #     notification["recipient"] = user.mobile_number

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
