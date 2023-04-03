import os
from notifications_python_client.errors import APIError
from notifications_python_client.notifications import NotificationsAPIClient
from app.models import (
    EMAIL_TYPE,
    KEY_TYPE_TEST,
    NOTIFICATION_CREATED,
    SMS_TYPE,
)

from flask import current_app


# development api key: emergency_alerts_service_development-09669d05-4d2e-4d9d-a803-b665c102c39c-cdc9f73c-ed51-4d57-99cd-70e418b8ddf5
api_key = os.environ.get("NOTIFY_CLIENT_API_KEY", "emergency_alerts_service_development-09669d05-4d2e-4d9d-a803-b665c102c39c-cdc9f73c-ed51-4d57-99cd-70e418b8ddf5")
notify_client = NotificationsAPIClient(api_key)


def get_notify_template(id):
    response = notify_client.get_template(id)
    if (response == None):
        raise APIError(f"Template {id} not found")
    return response

def notify_send(notification, research_mode=False):
    if research_mode:
        pass # TBD: what is research mode?

    try:
        response = None
        if notification['type'] == SMS_TYPE:
            response = notify_client.send_sms_notification(
                phone_number=notification['recipient'],
                template_id=notification['template_id'],
                personalisation=notification['personalisation'],
            )
        if notification['type'] == EMAIL_TYPE:
            response = notify_client.send_email_notification(
                email_address=notification['recipient'],
                template_id=notification['template_id'],
                personalisation=notification['personalisation'],
                email_reply_to_id=notification['reply_to'],
            )
    except Exception as e:
        current_app.logger.exception("Error sending notification: %s", e)

    return response

# send sms response
# {
#   "id": "740e5834-3a29-46b4-9a6f-16142fde533a",
#   "reference": "STRING",
#   "content": {
#     "body": "MESSAGE TEXT",
#     "from_number": "SENDER"
#   },
#   "uri": "https://api.notifications.service.gov.uk/v2/notifications/740e5834-3a29-46b4-9a6f-16142fde533a",
#   "template": {
#     "id": 'f33517ff-2a88-4f6e-b855-c550268ce08a',
#     "version": INTEGER,
#     "uri": "https://api.notifications.service.gov.uk/v2/template/ceb50d92-100d-4b8b-b559-14fa3b091cd"
#   }
# }

# send email response
# {
#   "id": "740e5834-3a29-46b4-9a6f-16142fde533a",
#   "reference": "STRING",
#   "content": {
#     "subject": "SUBJECT TEXT",
#     "body": "MESSAGE TEXT",
#     "from_email": "SENDER EMAIL"
#   },
#   "uri": "https://api.notifications.service.gov.uk/v2/notifications/740e5834-3a29-46b4-9a6f-16142fde533a",
#   "template": {
#     "id": "f33517ff-2a88-4f6e-b855-c550268ce08a",
#     "version": INTEGER,
#     "uri": "https://api.notifications.service.gov.uk/v2/template/f33517ff-2a88-4f6e-b855-c550268ce08a"
#   }
# }
