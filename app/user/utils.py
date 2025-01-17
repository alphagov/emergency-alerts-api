from emergency_alerts_utils.validation import (
    InvalidPhoneError,
    is_uk_phone_number,
    validate_email_address,
    validate_phone_number,
)
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
        else:
            try:
                if field == "mobile_number":
                    validate_mobile_number(updated_value)
                elif field == "email_address":
                    validate_email_address(updated_value)
            except Exception as error:
                return (
                    jsonify({"errors": [f"{error}"]}),
                    400,
                )

    return None


def validate_mobile_number(mobile_number):
    try:
        validate_phone_number(mobile_number, international=not (is_uk_phone_number(mobile_number)))
    except InvalidPhoneError as error:
        return (
            jsonify({"errors": [f"{error}"]}),
            400,
        )
    return None
