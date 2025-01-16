from flask import current_app, jsonify

from app.clients.notify_client import notify_send
from app.models import EMAIL_TYPE, SMS_TYPE


def send_security_change_email(template_id, email, reply_to, name, security_measure):
    notification = {
        "type": EMAIL_TYPE,
        "template_id": template_id,
        "recipient": email,
        "reply_to": reply_to,
        "personalisation": {
            "name": name,
            "security_measure": security_measure,
            "feedback_url": current_app.config["ADMIN_EXTERNAL_URL"] + "/support",
        },
    }
    notify_send(notification)


def send_security_change_sms(mobile_number, sent_to_text):
    notification = {
        "type": SMS_TYPE,
        "template_id": current_app.config["SECURITY_INFO_CHANGE_SMS_TEMPLATE_ID"],
        "recipient": mobile_number,
        "personalisation": {"sent_to": sent_to_text},
    }
    notify_send(notification)


def validate_field(field, current_value, updated_value, req_json):
    if field in req_json:
        field_str = field.replace("_", " ")
        updated_value = req_json[field]
        if updated_value == "":
            return (
                jsonify({"errors": [f"Enter a valid {field_str}"]}),
                400,
            )
        elif updated_value == current_value:
            return (
                jsonify({"errors": [f"{field_str.capitalize()} must be different to current {field_str}"]}),
                400,
            )
    return None
