import random
import string
import uuid

from app.dao.password_history_dao import (
    dao_create_password_for_user_id,
    dao_delete_all_historic_passwords_for_user,
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


def test_delete_passwords_deletes_passwords_from_password_history(notify_db_session):
    """
    Adds 2 passwords and then deletes them from PasswordHistory and checks that they're
    no longer in the table.
    """

    assert len(dao_get_all_passwords_for_user(test_uuid)) == 0

    random_password_1 = "".join(
        [random.choice(string.ascii_letters + string.digits + string.punctuation) for _ in range(15)]
    )
    random_password_2 = "".join(
        [random.choice(string.ascii_letters + string.digits + string.punctuation) for _ in range(15)]
    )
    dao_create_password_for_user_id(test_uuid, random_password_1)
    dao_create_password_for_user_id(test_uuid, random_password_2)

    assert len(dao_get_all_passwords_for_user(test_uuid)) == 2

    dao_delete_all_historic_passwords_for_user(test_uuid)
    assert len(dao_get_all_passwords_for_user(test_uuid)) == 0
