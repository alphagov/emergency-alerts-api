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
from flask import url_for
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
