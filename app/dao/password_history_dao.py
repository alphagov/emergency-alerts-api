from datetime import datetime

from app import db
from app.models import PasswordHistory


def dao_create_password_for_user_id(user_id, password):
    data = PasswordHistory(
        user_id=user_id,
        password=password,
        password_changed_at=datetime.now(),
    )
    db.session.add(data)
    db.session.commit()
    return PasswordHistory.query.filter_by(user_id=user_id).first()


def dao_get_all_passwords_for_user(user_id):
    return PasswordHistory.query.filter_by(user_id=user_id).all()


def dao_purge_password_history(user_id):
    PasswordHistory.query.filter_by(user_id=user_id).delete()
    db.session.commit()
