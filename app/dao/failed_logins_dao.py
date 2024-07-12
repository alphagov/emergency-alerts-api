from datetime import datetime, timedelta

from sqlalchemy import desc

from app import db
from app.models import FailedLogin


def dao_get_failed_logins():
    return FailedLogin.query.all()


def dao_create_failed_login_for_ip(ip):
    data = FailedLogin(
        ip=ip,
        attempted_at=datetime.now(),
    )
    db.session.add(data)
    db.session.commit()
    return FailedLogin.query.filter_by(ip=ip).first()


def dao_get_latest_failed_login_by_ip(ip):
    return FailedLogin.query.filter_by(ip=ip).order_by(desc(FailedLogin.attempted_at)).first() or None


def dao_get_count_of_all_failed_logins_for_ip(ip, time_period=1):
    current_time = datetime.now()
    return (
        FailedLogin.query.filter_by(ip=ip)
        .filter(FailedLogin.attempted_at >= current_time - timedelta(hours=time_period))
        .count()
    )


def dao_delete_all_failed_logins_for_ip(ip):
    FailedLogin.query.filter_by(ip=ip).delete()
    db.session.commit()
