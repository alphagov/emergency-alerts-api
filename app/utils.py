import ipaddress
import json
import os
from datetime import datetime, timedelta

import pytz
from emergency_alerts_utils.template import (
    BroadcastMessageTemplate,
    HTMLEmailTemplate,
    LetterPrintTemplate,
    SMSMessageTemplate,
)
from emergency_alerts_utils.timezones import convert_bst_to_utc
from emergency_alerts_utils.url_safe_token import generate_token
from flask import current_app, request, url_for
from sqlalchemy import func

DATETIME_FORMAT_NO_TIMEZONE = "%Y-%m-%d %H:%M:%S.%f"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DATE_FORMAT = "%Y-%m-%d"
local_timezone = pytz.timezone("Europe/London")


def pagination_links(pagination, endpoint, **kwargs):
    if "page" in kwargs:
        kwargs.pop("page", None)
    links = {}
    if pagination.has_prev:
        links["prev"] = url_for(endpoint, page=pagination.prev_num, **kwargs)
    if pagination.has_next:
        links["next"] = url_for(endpoint, page=pagination.next_num, **kwargs)
        links["last"] = url_for(endpoint, page=pagination.pages, **kwargs)
    return links


def get_prev_next_pagination_links(current_page, next_page_exists, endpoint, **kwargs):
    if "page" in kwargs:
        kwargs.pop("page", None)
    links = {}
    if current_page > 1:
        links["prev"] = url_for(endpoint, page=current_page - 1, **kwargs)
    if next_page_exists:
        links["next"] = url_for(endpoint, page=current_page + 1, **kwargs)
    return links


def url_with_token(data, url, config, base_url=None):
    token = generate_token(data, config["SECRET_KEY"], config["DANGEROUS_SALT"])
    base_url = (base_url or config["ADMIN_EXTERNAL_URL"]) + url
    return base_url + token


def get_template_instance(template, values):
    from app.models import BROADCAST_TYPE, EMAIL_TYPE, LETTER_TYPE, SMS_TYPE

    return {
        SMS_TYPE: SMSMessageTemplate,
        EMAIL_TYPE: HTMLEmailTemplate,
        LETTER_TYPE: LetterPrintTemplate,
        BROADCAST_TYPE: BroadcastMessageTemplate,
    }[template["template_type"]](template, values)


def get_london_midnight_in_utc(date):
    """
    This function converts date to midnight as BST (British Standard Time) to UTC,
    the tzinfo is lastly removed from the datetime because the database stores the timestamps without timezone.
    :param date: the day to calculate the London midnight in UTC for
    :return: the datetime of London midnight in UTC, for example 2016-06-17 = 2016-06-16 23:00:00
    """
    return convert_bst_to_utc(datetime.combine(date, datetime.min.time()))


def get_midnight_for_day_before(date):
    day_before = date - timedelta(1)
    return get_london_midnight_in_utc(day_before)


def get_london_month_from_utc_column(column):
    """
    Where queries need to count notifications by month it needs to be
    the month in BST (British Summer Time).
    The database stores all timestamps as UTC without the timezone.
     - First set the timezone on created_at to UTC
     - then convert the timezone to BST (or Europe/London)
     - lastly truncate the datetime to month with which we can group
       queries
    """
    return func.date_trunc("month", func.timezone("Europe/London", func.timezone("UTC", column)))


def get_public_notify_type_text(notify_type, plural=False):
    from app.models import (
        BROADCAST_TYPE,
        PRECOMPILED_LETTER,
        SMS_TYPE,
        UPLOAD_DOCUMENT,
    )

    notify_type_text = notify_type
    if notify_type == SMS_TYPE:
        notify_type_text = "text message"
    elif notify_type == UPLOAD_DOCUMENT:
        notify_type_text = "document"
    elif notify_type == PRECOMPILED_LETTER:
        notify_type_text = "precompiled letter"
    elif notify_type == BROADCAST_TYPE:
        notify_type_text = "broadcast message"

    return "{}{}".format(notify_type_text, "s" if plural else "")


def midnight_n_days_ago(number_of_days):
    """
    Returns midnight a number of days ago. Takes care of daylight savings etc.
    """
    return get_london_midnight_in_utc(datetime.utcnow() - timedelta(days=number_of_days))


def escape_special_characters(string):
    for special_character in ("\\", "_", "%", "/"):
        string = string.replace(special_character, r"\{}".format(special_character))
    return string


def email_address_is_nhs(email_address):
    return email_address.lower().endswith(
        (
            "@nhs.uk",
            "@nhs.net",
            ".nhs.uk",
            ".nhs.net",
        )
    )


def get_archived_db_column_value(column):
    date = datetime.utcnow().strftime("%Y-%m-%d")
    return f"_archived_{date}_{column}"


def get_dt_string_or_none(val):
    return val.strftime(DATETIME_FORMAT) if val else None


def get_interval_seconds_or_none(val):
    return val.total_seconds() if val else None


def get_uuid_string_or_none(val):
    return str(val) if val else None


def format_sequential_number(sequential_number):
    return format(sequential_number, "x").zfill(8)


def is_local_host():
    return current_app.config["HOST"] == "local"


def is_cloud_host():
    return not is_local_host()


def is_private_environment():
    return os.environ.get("ENVIRONMENT") in ["local", "development", "preview"]


def is_public_environment():
    return not is_private_environment()


def log_auth_activity(user, message, admin_only=True):
    from app.models import User

    if isinstance(user, User):
        data = {
            "user_id": user.id,
            "user_name": user.name,
            "email_address": user.email_address,
            "auth_type": user.auth_type,
            "platform_admin": user.platform_admin,
            "failed_login_count": user.failed_login_count,
            "current_session_id": user.current_session_id,
        }
    else:
        data = {"email_address": user}

    if (admin_only and user.platform_admin) or (not admin_only):
        current_app.logger.info(
            message,
            extra=data,
        )


def log_user(user, message):
    # Guards against the reserved keyword under the `info` method.
    if "name" in user:
        user["user_name"] = user.pop("name")
    current_app.logger.info(
        message,
        extra=user,
    )


def get_ip_address():
    ip = None
    if current_app.config["HOST"] == "local":
        ip = request.remote_addr
    elif current_app.config["HOST"] == "hosted":
        ip = request.headers.get("X-Forwarded-For")
    elif current_app.config["HOST"] == "test":
        ip = "127.0.0.1"
    return ip


def calculate_delay_period(failed_login_count):
    return 10 * (2 ** (failed_login_count - 1)) if failed_login_count < 4 else 120


def check_ip_should_be_throttled(ip):
    if cidr_ranges := json.loads(os.environ.get("RATE_LIMIT_EXCEPTION_IPS", "[]")):
        return all((ipaddress.ip_address(ip) not in ipaddress.ip_network(range)) for range in cidr_ranges)
    else:
        return True
