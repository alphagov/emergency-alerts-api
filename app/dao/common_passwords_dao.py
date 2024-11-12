from app import db
from app.models import CommonPasswords


def dao_get_common_password_by_password(password):
    return CommonPasswords.query.filter_by(password=password).first()


def dao_create_common_password(password):
    data = CommonPasswords(password=password)
    db.session.add(data)
    db.session.commit()
    return CommonPasswords.query.filter_by(password=password).first()
