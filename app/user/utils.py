from emergency_alerts_utils.validation import (
    InvalidEmailError,
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


def validate_field(field, current_value, updated_value, data, field_label):
    updated_value = data[field]
    if updated_value == "" or updated_value is None:
        if field_label == "name":
            return (
                jsonify({"errors": ["Enter a name"]}),
                400,
            )
        else:
            return (
                jsonify({"errors": [f"Enter a valid {field_label}"]}),
                400,
            )
    elif updated_value == current_value:
        return (
            jsonify({"errors": [f"{field_label.capitalize()} must be different to current {field_label}"]}),
            400,
        )
    else:
        try:
            if field_label == "mobile number":
                validate_mobile_number(updated_value)
            elif field_label == "email address":
                try:
                    validate_email_address(updated_value)
                except InvalidEmailError:
                    raise InvalidEmailError("Enter a valid email address")
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
