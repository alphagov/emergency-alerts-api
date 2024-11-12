from app.dao.common_passwords_dao import dao_get_common_password_by_password
from app.models import CommonPasswords


def test_get_common_password_by_password(notify_db_session):
    """
    Creates common password record and checks that it is returned in dao_get_common_password_by_password
    if it exists in table.
    """
    common_password = CommonPasswords(password="TEST")
    notify_db_session.add(common_password)
    notify_db_session.commit()

    assert dao_get_common_password_by_password("TEST") == "TEST"
    assert dao_get_common_password_by_password("TEST2") is None
