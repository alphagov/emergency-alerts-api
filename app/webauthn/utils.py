from flask import current_app

from app.clients.notify_client import notify_send
from app.models import EMAIL_TYPE


def send_security_key_change_email(email, reply_to, name, change_made, security_key_change, security_key_change_text):
    notification = {
        "type": EMAIL_TYPE,
        "template_id": current_app.config["SECURITY_KEY_CHANGE_EMAIL_TEMPLATE_ID"],
        "recipient": email,
        "reply_to": reply_to,
        "personalisation": {
            "name": name,
            "change_made": change_made,
            "security_key_change": security_key_change,
            "security_key_change_text": security_key_change_text,
            "feedback_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/support",
        },
    }
    notify_send(notification)
