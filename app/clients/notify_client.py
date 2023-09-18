import os

from flask import current_app
from notifications_python_client.errors import APIError
from notifications_python_client.notifications import NotificationsAPIClient

from app.models import EMAIL_TYPE, SMS_TYPE


class Notify:
    pass


__notify = Notify()
__notify.client = None


def get_notify_client():
    if current_app.config["NOTIFY_ENVIRONMENT"] == "development":
        return

    try:
        api_key = os.environ.get("NOTIFY_CLIENT_API_KEY", "empty_key")
        __notify.client = NotificationsAPIClient(api_key)
    except TypeError:
        current_app.logger.exception("NotificationsAPIClient API key required", extra={"python_module": __name__})
    except AssertionError:
        current_app.logger.exception("Invalid API key format", extra={"python_module": __name__})


def get_notify_template(id):
    if current_app.config["NOTIFY_ENVIRONMENT"] == "development":
        return

    if __notify.client is None:
        get_notify_client()

    response = __notify.client.get_template(id)

    if response is None:
        raise APIError(f"Template {id} not found")

    return response


def notify_send(notification):
    if current_app.config["NOTIFY_ENVIRONMENT"] == "development":
        return

    if __notify.client is None:
        get_notify_client()

    try:
        response = None
        if notification["type"] == SMS_TYPE:
            response = __notify.client.send_sms_notification(
                phone_number=notification["recipient"],
                template_id=notification["template_id"],
                personalisation=notification["personalisation"],
            )
        if notification["type"] == EMAIL_TYPE:
            response = __notify.client.send_email_notification(
                email_address=notification["recipient"],
                template_id=notification["template_id"],
                personalisation=notification["personalisation"],
                email_reply_to_id=notification["reply_to"],
            )
    except Exception:
        current_app.logger.exception("Error sending notification", extra={"python_module": __name__})

    return response
