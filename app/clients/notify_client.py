import os
from notifications_python_client.notifications import NotificationsAPIClient
from app.models import (
    EMAIL_TYPE,
    INTERNATIONAL_POSTAGE_TYPES,
    KEY_TYPE_TEST,
    LETTER_TYPE,
    NOTIFICATION_CREATED,
    SMS_TYPE,
    Notification,
)

from app.dao.notifications_dao import dao_delete_notifications_by_id


# development api key: emergency_alerts_service_development-09669d05-4d2e-4d9d-a803-b665c102c39c-cdc9f73c-ed51-4d57-99cd-70e418b8ddf5
api_key = os.environ.get("NOTIFY_CLIENT_API_KEY")
notify_client = NotificationsAPIClient(api_key)


def notify_send(notification, research_mode=False):
    if research_mode or notification.key_type == KEY_TYPE_TEST:
        pass # TBD: what is research mode?

    try:
        response = None
        if notification.notification_type == SMS_TYPE:
            notify_client.send_sms_notification(
                phone_number='',
                template_id=notification.template.id,
                personalisation=notification.personalisation,
            )

        if notification.notification_type == EMAIL_TYPE:
            notify_client.send_email_notification(
                email_address=notification.recipient,
                template_id=notification.template.id,
                personalisation=notification.personalisation,
                email_reply_to_id=notification.service.get_default_reply_to_email_id(),
            )
    except Exception as e:
        dao_delete_notifications_by_id(notification.notification_id)

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
