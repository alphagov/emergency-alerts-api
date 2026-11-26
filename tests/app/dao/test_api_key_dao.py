from datetime import date, datetime, timedelta, timezone

import pytest
from emergency_alerts_utils.api_key import KEY_TYPE_NORMAL
from freezegun import freeze_time
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao.api_key_dao import (
    dao_get_api_keys_needing_expiry_warning,
    dao_record_api_key_expiry_warning_sent,
    expire_api_key,
    get_model_api_keys,
    get_unsigned_secret,
    get_unsigned_secrets,
    purge_test_api_keys,
    save_model_api_key,
)
from app.models import ApiKey
from tests.app.db import create_api_key


def test_save_api_key_should_create_new_api_key_and_history(sample_service):
    api_key = ApiKey(
        **{
            "service": sample_service,
            "name": sample_service.name,
            "created_by": sample_service.created_by,
            "key_type": KEY_TYPE_NORMAL,
        }
    )
    save_model_api_key(api_key)

    all_api_keys = get_model_api_keys(service_id=sample_service.id)
    assert len(all_api_keys) == 1
    assert all_api_keys[0] == api_key
    assert api_key.version == 1

    all_history = api_key.get_history_model().query.all()
    assert len(all_history) == 1
    assert all_history[0].id == api_key.id
    assert all_history[0].version == api_key.version


def test_expire_api_key_should_update_the_api_key_and_create_history_record(notify_api, sample_api_key):
    expire_api_key(service_id=sample_api_key.service_id, api_key_id=sample_api_key.id)
    all_api_keys = get_model_api_keys(service_id=sample_api_key.service_id)
    assert len(all_api_keys) == 1
    assert all_api_keys[0].expiry_date <= datetime.now()
    assert all_api_keys[0].secret == sample_api_key.secret
    assert all_api_keys[0].id == sample_api_key.id
    assert all_api_keys[0].service_id == sample_api_key.service_id

    all_history = sample_api_key.get_history_model().query.all()
    assert len(all_history) == 2
    assert all_history[0].id == sample_api_key.id
    assert all_history[1].id == sample_api_key.id
    sorted_all_history = sorted(all_history, key=lambda hist: hist.version)
    sorted_all_history[0].version = 1
    sorted_all_history[1].version = 2


def test_get_api_key_should_raise_exception_when_api_key_does_not_exist(sample_service, fake_uuid):
    with pytest.raises(NoResultFound):
        get_model_api_keys(sample_service.id, id=fake_uuid)


def test_should_return_api_key_for_service(notify_api, notify_db_session, sample_api_key):
    api_key = get_model_api_keys(service_id=sample_api_key.service_id, id=sample_api_key.id)
    assert api_key == sample_api_key


def test_should_return_unsigned_api_keys_for_service_id(sample_api_key):
    unsigned_api_key = get_unsigned_secrets(sample_api_key.service_id)
    assert len(unsigned_api_key) == 1
    assert sample_api_key._secret != unsigned_api_key[0]
    assert unsigned_api_key[0] == sample_api_key.secret


def test_get_unsigned_secret_returns_key(sample_api_key):
    unsigned_api_key = get_unsigned_secret(sample_api_key.id)
    assert sample_api_key._secret != unsigned_api_key
    assert unsigned_api_key == sample_api_key.secret


def test_should_not_allow_duplicate_key_names_per_service(sample_api_key, fake_uuid):
    api_key = ApiKey(
        **{
            "id": fake_uuid,
            "service": sample_api_key.service,
            "name": sample_api_key.name,
            "created_by": sample_api_key.created_by,
            "key_type": KEY_TYPE_NORMAL,
        }
    )
    with pytest.raises(IntegrityError):
        save_model_api_key(api_key)


def test_save_api_key_can_create_key_with_same_name_if_other_is_expired(sample_service):
    expired_api_key = ApiKey(
        **{
            "service": sample_service,
            "name": "normal api key",
            "created_by": sample_service.created_by,
            "key_type": KEY_TYPE_NORMAL,
            "expiry_date": datetime.now(timezone.utc),
        }
    )
    save_model_api_key(expired_api_key)
    api_key = ApiKey(
        **{
            "service": sample_service,
            "name": "normal api key",
            "created_by": sample_service.created_by,
            "key_type": KEY_TYPE_NORMAL,
        }
    )
    save_model_api_key(api_key)
    keys = ApiKey.query.all()
    assert len(keys) == 2


def test_save_api_key_should_not_create_new_service_history(sample_service):
    from app.models import Service

    assert Service.query.count() == 1
    assert Service.get_history_model().query.count() == 1

    api_key = ApiKey(
        **{
            "service": sample_service,
            "name": sample_service.name,
            "created_by": sample_service.created_by,
            "key_type": KEY_TYPE_NORMAL,
        }
    )
    save_model_api_key(api_key)

    assert Service.get_history_model().query.count() == 1


@pytest.mark.parametrize("days_old, expected_length", [(5, 1), (8, 0)])
def test_should_not_return_revoked_api_keys_older_than_7_days(sample_service, days_old, expected_length):
    expired_api_key = ApiKey(
        **{
            "service": sample_service,
            "name": sample_service.name,
            "created_by": sample_service.created_by,
            "key_type": KEY_TYPE_NORMAL,
            "expiry_date": datetime.now(timezone.utc) - timedelta(days=days_old),
        }
    )
    save_model_api_key(expired_api_key)

    all_api_keys = get_model_api_keys(service_id=sample_service.id)

    assert len(all_api_keys) == expected_length


def test_dao_purge_test_api_keys(sample_service):
    key1 = ApiKey(
        name="Kept-123",
        _secret="kept123",
        service_id=sample_service.id,
        key_type="normal",
        created_by=sample_service.created_by,
    )
    key2 = ApiKey(
        name="Key-123",
        _secret="key123",
        service_id=sample_service.id,
        key_type="normal",
        created_by=sample_service.created_by,
    )

    save_model_api_key(key1)
    save_model_api_key(key2)

    keys = get_model_api_keys(sample_service.id)
    assert len(keys) == 2
    history_keys = ApiKey.get_history_model().query.filter(ApiKey.service_id == sample_service.id).all()
    assert len(history_keys) == 2

    purge_test_api_keys(sample_service.id)

    keys = get_model_api_keys(sample_service.id)
    assert len(keys) == 1
    assert keys[0].name == "Kept-123"
    history_keys = ApiKey.get_history_model().query.filter(ApiKey.service_id == sample_service.id).all()
    assert len(history_keys) == 1


def _create_api_key_created_at(service, created_at, **kwargs):
    api_key = create_api_key(service, key_name=f"key created {created_at}", **kwargs)
    api_key.created_at = created_at
    db.session.commit()
    return api_key


def test_dao_get_api_keys_needing_expiry_warning_returns_keys_within_28_days_of_expiry(sample_service):
    today = date(2026, 11, 26)
    # Scheduled expiry is 12 months after creation, so 28 days from today means created on 2025-12-24
    exactly_28_days_left = _create_api_key_created_at(sample_service, datetime(2025, 12, 24, 23, 59))
    ten_days_left = _create_api_key_created_at(sample_service, datetime(2025, 12, 6, 9, 0))
    already_expired = _create_api_key_created_at(sample_service, datetime(2025, 6, 1, 9, 0))
    _create_api_key_created_at(sample_service, datetime(2025, 12, 25, 0, 0))  # 29 days left
    _create_api_key_created_at(sample_service, datetime(2026, 11, 1, 9, 0))  # brand new

    assert dao_get_api_keys_needing_expiry_warning(today) == [already_expired, ten_days_left, exactly_28_days_left]


def test_dao_get_api_keys_needing_expiry_warning_ignores_revoked_keys(sample_service):
    api_key = _create_api_key_created_at(sample_service, datetime(2025, 6, 1, 9, 0))
    expire_api_key(service_id=sample_service.id, api_key_id=api_key.id)

    assert dao_get_api_keys_needing_expiry_warning(date(2026, 11, 26)) == []


def test_dao_get_api_keys_needing_expiry_warning_ignores_keys_already_warned_about(sample_service):
    api_key = _create_api_key_created_at(sample_service, datetime(2025, 12, 1, 9, 0))
    assert dao_get_api_keys_needing_expiry_warning(date(2026, 11, 26)) == [api_key]

    dao_record_api_key_expiry_warning_sent(api_key)

    assert dao_get_api_keys_needing_expiry_warning(date(2026, 11, 26)) == []


@freeze_time("2026-11-26 09:00:00")
def test_dao_record_api_key_expiry_warning_sent_does_not_create_a_new_version(sample_api_key):
    dao_record_api_key_expiry_warning_sent(sample_api_key)

    saved = ApiKey.query.filter_by(id=sample_api_key.id).one()
    assert saved.expiry_warning_sent_at == datetime(2026, 11, 26, 9, 0)
    assert saved.version == 1
    assert ApiKey.get_history_model().query.filter_by(id=sample_api_key.id).count() == 1
