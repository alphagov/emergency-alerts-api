import uuid

from app.dao.password_history_dao import (
    dao_create_password_for_user_id,
    dao_get_all_passwords_for_user,
)
from app.hashing import check_hash

test_uuid = uuid.uuid4()
test_password = "test"


def test_get_password_history_returns_all_past_passwords(notify_db_session):
    """
    Creates 3 password records in PasswordHistory table and checks that 3 records are
    returned in dao_get_all_passwords_for_user.
    """
    dao_create_password_for_user_id(test_uuid, test_password)
    dao_create_password_for_user_id(test_uuid, test_password)
    dao_create_password_for_user_id(test_uuid, test_password)
    response = dao_get_all_passwords_for_user(test_uuid)
    assert len(response) == 3


def test_creates_passwords_adds_passwords_to_password_history(notify_db_session):
    """
    Creates 2 password records in PasswordHistory and checks that the second password
    stored is the same as the second password added within tests.
    """
    dao_create_password_for_user_id(test_uuid, test_password)
    dao_create_password_for_user_id(test_uuid, f"{test_password}1")
    assert check_hash(
        f"{test_password}1",
        dao_get_all_passwords_for_user(test_uuid)[1]._password,
    )
