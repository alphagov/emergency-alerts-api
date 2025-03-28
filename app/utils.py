import os
from datetime import datetime, timedelta, timezone

import pytz
from emergency_alerts_utils.url_safe_token import generate_token
from flask import current_app, request

DATETIME_FORMAT_NO_TIMEZONE = "%Y-%m-%d %H:%M:%S.%f"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DATE_FORMAT = "%Y-%m-%d"
local_timezone = pytz.timezone("Europe/London")


def url_with_token(data, url, config, base_url=None):
    token = generate_token(data, config["SECRET_KEY"], config["DANGEROUS_SALT"])
    base_url = (base_url or config["ADMIN_EXTERNAL_URL"]) + url
    return base_url + token


def get_public_notify_type_text(notify_type, plural=False):
    notify_type_text = notify_type
    if notify_type == "broadcast":
        notify_type_text = "broadcast message"

    return "{}{}".format(notify_type_text, "s" if plural else "")


def escape_special_characters(string):
    for special_character in ("\\", "_", "%", "/"):
        string = string.replace(special_character, r"\{}".format(special_character))
    return string


def get_archived_db_column_value(column):
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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


def log_throttled_login(ip):
    data = {"ip": ip, "attempted_at": datetime.now()}
    current_app.logger.info(
        "User login throttled",
        extra=data,
    )


def get_ip_address():
    if x_forwarded_for_ips := request.headers.get("X-Forwarded-For"):
        return [ip.strip() for ip in x_forwarded_for_ips.split(",")][0]
    else:
        return request.remote_addr


def calculate_delay_period(failed_login_count):
    if failed_login_count == 1:
        delay = 0
    elif failed_login_count == 2:
        delay = 1
    elif failed_login_count == 3:
        delay = 2
    else:
        delay = 2 * calculate_delay_period(failed_login_count - 1)
    return min(delay, current_app.config["MAX_THROTTLE_PERIOD"])


def check_request_within_throttle_period(login_attempt, delay_period):
    return datetime.now() - login_attempt.attempted_at < timedelta(seconds=delay_period)
