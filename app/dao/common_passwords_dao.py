from app.models import CommonPasswords


def get_common_password_by_password(password):
    return CommonPasswords.query.filter_by(password=password).first()
