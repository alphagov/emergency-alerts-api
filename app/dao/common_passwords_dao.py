from app.models import CommonPasswords


def dao_get_common_password_by_password(password):
    return CommonPasswords.query.filter_by(password=password).first()
