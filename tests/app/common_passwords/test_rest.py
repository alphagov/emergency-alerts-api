from app.common_passwords.rest import is_password_common
from app.models import CommonPasswords


def test_is_password_common(notify_db_session, admin_request, mocker):
    """
    Asserts that the password is or isn't in the common password table.
    """
    assert is_password_common("TEST") is False

    common_password = CommonPasswords(passwordattempted_at="TEST")
    notify_db_session.add(common_password)
    notify_db_session.commit()

    assert is_password_common("TEST") is True
    assert is_password_common("TEST2") is False
