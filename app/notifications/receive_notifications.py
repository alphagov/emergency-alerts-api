from datetime import datetime
from urllib.parse import unquote

import iso8601
from emergency_alerts_utils.recipients import (
    try_validate_and_format_phone_number,
)
from flask import Blueprint, current_app
from gds_metrics.metrics import Counter

from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.dao.services_dao import dao_fetch_service_by_inbound_number
from app.errors import register_errors
from app.models import INBOUND_SMS_TYPE, SMS_TYPE, InboundSms

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


def create_inbound_sms_object(service, content, from_number, provider_ref, date_received, provider_name):
    user_number = try_validate_and_format_phone_number(
        from_number, international=True, log_msg=f'Invalid from_number received for service "{service.id}"'
    )

    provider_date = date_received
    if provider_date:
        provider_date = format_mmg_datetime(provider_date)

    inbound = InboundSms(
        service=service,
        notify_number=service.get_inbound_number(),
        user_number=user_number,
        provider_date=provider_date,
        provider_reference=provider_ref,
        content=content,
        provider=provider_name,
    )
    dao_create_inbound_sms(inbound)
    return inbound


def fetch_potential_service(inbound_number, provider_name):
    service = dao_fetch_service_by_inbound_number(inbound_number)

    if not service:
        current_app.logger.warning(
            'Inbound number "{}" from {} not associated with a service'.format(inbound_number, provider_name)
        )
        return False

    if not has_inbound_sms_permissions(service.permissions):
        current_app.logger.error('Service "{}" does not allow inbound SMS'.format(service.id))
        return False

    return service


def has_inbound_sms_permissions(permissions):
    str_permissions = [p.permission for p in permissions]
    return set([INBOUND_SMS_TYPE, SMS_TYPE]).issubset(set(str_permissions))


def strip_leading_forty_four(number):
    if number.startswith("44"):
        return number.replace("44", "0", 1)
    return number
