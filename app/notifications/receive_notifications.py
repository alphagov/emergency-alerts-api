from datetime import datetime
from urllib.parse import unquote

import iso8601
from flask import Blueprint
from gds_metrics.metrics import Counter

from app.errors import register_errors
from app.models import INBOUND_SMS_TYPE, SMS_TYPE

receive_notifications_blueprint = Blueprint("receive_notifications", __name__)
register_errors(receive_notifications_blueprint)


INBOUND_SMS_COUNTER = Counter("inbound_sms", "Total number of inbound SMS received", ["provider"])


def format_mmg_message(message):
    return unescape_string(unquote(message.replace("+", " ")))


def unescape_string(string):
    return string.encode("raw_unicode_escape").decode("unicode_escape")


def format_mmg_datetime(date):
    """
    We expect datetimes in format 2017-05-21+11%3A56%3A11 - ie, spaces replaced with pluses, and URI encoded
    and in UTC
    """
    try:
        orig_date = format_mmg_message(date)
        parsed_datetime = iso8601.parse_date(orig_date).replace(tzinfo=None)
        return parsed_datetime
    except iso8601.ParseError:
        return datetime.utcnow()


def has_inbound_sms_permissions(permissions):
    str_permissions = [p.permission for p in permissions]
    return set([INBOUND_SMS_TYPE, SMS_TYPE]).issubset(set(str_permissions))


def strip_leading_forty_four(number):
    if number.startswith("44"):
        return number.replace("44", "0", 1)
    return number
