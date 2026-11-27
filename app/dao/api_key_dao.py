import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app import db
from app.dao.dao_utils import autocommit, version_class
from app.models import API_KEY_EXPIRY_WARNING_DAYS, ApiKey


@autocommit
@version_class(ApiKey)
def save_model_api_key(api_key):
    if not api_key.id:
        api_key.id = uuid.uuid4()  # must be set now so version history model can use same id
    api_key.secret = uuid.uuid4()
    db.session.add(api_key)


@autocommit
@version_class(ApiKey)
def expire_api_key(service_id, api_key_id):
    api_key = ApiKey.query.filter_by(id=api_key_id, service_id=service_id).one()
    api_key.expiry_date = datetime.now(timezone.utc)
    db.session.add(api_key)


def get_model_api_keys(service_id, id=None):
    if id:
        return ApiKey.query.filter_by(id=id, service_id=service_id, expiry_date=None).one()
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    return ApiKey.query.filter(
        or_(ApiKey.expiry_date == None, func.date(ApiKey.expiry_date) > seven_days_ago),  # noqa
        ApiKey.service_id == service_id,
    ).all()


def get_unsigned_secrets(service_id):
    """
    This method can only be exposed to the Authentication of the api calls.
    """
    api_keys = ApiKey.query.filter_by(service_id=service_id, expiry_date=None).all()
    keys = [x.secret for x in api_keys]
    return keys


def get_unsigned_secret(key_id):
    """
    This method can only be exposed to the Authentication of the api calls.
    """
    api_key = ApiKey.query.filter_by(id=key_id, expiry_date=None).one()
    return api_key.secret


def dao_get_api_keys_needing_expiry_warning(today):
    unwarned_active_keys = (
        ApiKey.query.filter(
            ApiKey.expiry_date.is_(None),
            ApiKey.expiry_warning_sent_at.is_(None),
        )
        .options(joinedload(ApiKey.service))
        .order_by(ApiKey.created_at)
        .all()
    )
    # Filtered here rather than in SQL so the calculated date is the same as the expiry date shown in the key
    warn_if_expiring_on_or_before = today + timedelta(days=API_KEY_EXPIRY_WARNING_DAYS)
    return [key for key in unwarned_active_keys if key.scheduled_expiry_date <= warn_if_expiring_on_or_before]


@autocommit
def dao_record_api_key_expiry_warning_sent(api_key):
    api_key.expiry_warning_sent_at = datetime.now(timezone.utc)
    db.session.add(api_key)


@autocommit
def purge_test_api_keys(service_id):
    # Only looks for Key-identifier, which is what the functional tests make
    ApiKey.query.filter(ApiKey.service_id == service_id, ApiKey.name.startswith("Key-")).delete(
        synchronize_session="fetch"
    )
    ApiKeyHistory = ApiKey.get_history_model()
    ApiKeyHistory.query.filter(ApiKeyHistory.service_id == service_id, ApiKeyHistory.name.startswith("Key-")).delete(
        synchronize_session="fetch"
    )
