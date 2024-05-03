import random
from datetime import datetime
from urllib import parse

from cachetools import TTLCache, cached
from flask import current_app

from app import notification_provider_clients
from app.dao.notifications_dao import dao_update_notification
from app.dao.provider_details_dao import (
    get_provider_details_by_notification_type,
)
from app.exceptions import NotificationTechnicalFailureException
from app.models import (
    NOTIFICATION_SENDING,
    NOTIFICATION_SENT,
    NOTIFICATION_STATUS_TYPES_COMPLETED,
    NOTIFICATION_TECHNICAL_FAILURE,
)


def update_notification_to_sending(notification, provider):
    notification.sent_at = datetime.utcnow()
    notification.sent_by = provider.name
    if notification.status not in NOTIFICATION_STATUS_TYPES_COMPLETED:
        notification.status = NOTIFICATION_SENT if notification.international else NOTIFICATION_SENDING
    dao_update_notification(notification)


provider_cache = TTLCache(maxsize=8, ttl=10)


@cached(cache=provider_cache)
def provider_to_use(notification_type, international=False):
    active_providers = [
        p for p in get_provider_details_by_notification_type(notification_type, international) if p.active
    ]

    if not active_providers:
        current_app.logger.error("{} failed as no active providers".format(notification_type))
        raise Exception("No active {} providers".format(notification_type))

    if len(active_providers) == 1:
        weights = [100]
    else:
        weights = [p.priority for p in active_providers]

    chosen_provider = random.choices(active_providers, weights=weights)[0]

    return notification_provider_clients.get_client_by_name_and_type(chosen_provider.identifier, notification_type)


def get_logo_url(base_url, logo_file):
    base_url = parse.urlparse(base_url)
    netloc = base_url.netloc

    if base_url.netloc.startswith("localhost"):
        netloc = "notify.tools"
    elif base_url.netloc.startswith("www"):
        # strip "www."
        netloc = base_url.netloc[4:]

    logo_url = parse.ParseResult(
        scheme=base_url.scheme,
        netloc="static-logos." + netloc,
        path=logo_file,
        params=base_url.params,
        query=base_url.query,
        fragment=base_url.fragment,
    )
    return parse.urlunparse(logo_url)


def technical_failure(notification):
    notification.status = NOTIFICATION_TECHNICAL_FAILURE
    dao_update_notification(notification)
    raise NotificationTechnicalFailureException(
        "Send {} for notification id {} to provider is not allowed: service {} is inactive".format(
            notification.notification_type, notification.id, notification.service_id
        )
    )
