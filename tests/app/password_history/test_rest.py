import uuid

from app.password_history.rest import (
    add_old_password_for_user,
    has_user_already_used_password,
)

test_user = uuid.uuid4()


def test_has_user_already_used_password(notify_db_session, admin_request, mocker):
    add_old_password_for_user(test_user, "test")
    add_old_password_for_user(test_user, "test2")
    assert has_user_already_used_password(test_user, "test") is True
    assert has_user_already_used_password(test_user, "test2") is True
    assert has_user_already_used_password(test_user, "test3") is False
