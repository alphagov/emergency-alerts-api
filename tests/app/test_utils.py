from datetime import datetime, timedelta

import pytest

from app.models import FailedLogin
from app.utils import format_sequential_number, get_interval_seconds_or_none


@pytest.mark.parametrize(
    "interval, expected_seconds",
    [
        (timedelta(hours=22, minutes=30), 81000),
        (timedelta(minutes=50), 3000),
        (timedelta(hours=3, seconds=5), 10805),
        (None, None),
    ],
)
def test_get_interval_seconds_or_none(interval, expected_seconds):
    assert get_interval_seconds_or_none(interval) == expected_seconds


def test_format_sequential_number():
    assert format_sequential_number(123) == "0000007b"


def create_failed_login_for_test(notify_db_session, ip):
    failed_login = FailedLogin(ip=ip, attempted_at=datetime.now())
    notify_db_session.add(failed_login)
    notify_db_session.commit()
