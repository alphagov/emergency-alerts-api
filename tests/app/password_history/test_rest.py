import uuid

from app.password_history.rest import (
    add_password_for_user,
    is_password_for_user_already_in_table,
)

test_user = uuid.uuid4()


def test_is_password_for_user_already_in_table(notify_db_session, admin_request, mocker):
    add_password_for_user(test_user, "test")
    add_password_for_user(test_user, "test2")
    assert is_password_for_user_already_in_table(test_user, "test") is True
    assert is_password_for_user_already_in_table(test_user, "test2") is True
    assert is_password_for_user_already_in_table(test_user, "test3") is False
