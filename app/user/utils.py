from emergency_alerts_utils.validation import (
    InvalidEmailError,
    InvalidPhoneError,
    is_uk_phone_number,
    validate_email_address,
    validate_phone_number,
)
from flask import current_app, jsonify

from app.clients.notify_client import notify_send
from app.dao.users_dao import get_user_by_id
from app.models import EMAIL_AUTH_TYPE, EMAIL_TYPE, SMS_TYPE


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


def send_security_change_notification(
    update_dict, user_to_update, updated_email_address=None, updated_mobile_number=None, existing_mobile_number=None
):
    security_measure = ""
    if "email_address" in update_dict and updated_email_address:
        security_measure = "email address"
        # Sending notification to previous email address
        send_security_change_email(
            current_app.config["SECURITY_INFO_CHANGE_EMAIL_TEMPLATE_ID"],
            user_to_update.email_address,
            current_app.config["EAS_EMAIL_REPLY_TO_ID"],
            user_to_update.name,
            "email address",
        )
    elif "mobile_number" in update_dict and updated_mobile_number:
        security_measure = "mobile number"
        # Sending notification to updated mobile number
        send_security_change_sms(user_to_update.mobile_number, "this phone")
        # Sending notification to previous mobile number
        if existing_mobile_number:
            send_security_change_sms(existing_mobile_number, "the requested phone")
    elif "name" in update_dict:
        security_measure = "name"
    return security_measure


def relevant_field_updated(user_to_update, req_json, field):
    return (
        not (
            (field == "mobile_number" and user_to_update.auth_type == EMAIL_AUTH_TYPE)
            or ((field == "mobile_number" and req_json.get("auth_type") == EMAIL_AUTH_TYPE))
        )
        and field in req_json
    )


def get_user_updated_by(req_json):
    return get_user_by_id(user_id=req_json.pop("updated_by")) if "updated_by" in req_json else None


def get_updated_attributes(req_json):
    updated_name = req_json.get("name")
    updated_mobile_number = req_json.get("mobile_number")
    updated_email_address = req_json.get("email_address")
    return updated_name, updated_mobile_number, updated_email_address


def get_existing_attributes(user_to_update):
    existing_email_address = user_to_update.email_address
    existing_mobile_number = user_to_update.mobile_number
    existing_name = user_to_update.name
    return existing_email_address, existing_mobile_number, existing_name


def send_updated_by_notification(update_dict, user_to_update, updated_by):
    notification = {}
    if "email_address" in update_dict:
        notification["type"] = EMAIL_TYPE
        notification["template_id"] = current_app.config["TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID"]
        notification["recipient"] = user_to_update.email_address
        notification["reply_to"] = current_app.config["EAS_EMAIL_REPLY_TO_ID"]
        notification = add_personalisation_to_notification(notification, user_to_update, updated_by)
        return notification
    elif "mobile_number" in update_dict:
        notification["type"] = SMS_TYPE
        notification["template_id"] = current_app.config["TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID"]
        notification["recipient"] = user_to_update.mobile_number
        notification = add_personalisation_to_notification(notification, user_to_update, updated_by)
        return notification
    else:
        return None


def add_personalisation_to_notification(notification, user_to_update, updated_by):
    notification["personalisation"] = {
        "name": user_to_update.name,
        "servicemanagername": updated_by.name,
        "email address": user_to_update.email_address,
    }
    return notification
