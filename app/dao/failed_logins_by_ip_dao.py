import datetime

from sqlalchemy import desc

from app import db
from app.models import FailedLoginCountByIP


def dao_get_failed_logins():
    return FailedLoginCountByIP.query.all()


def dao_create_failed_login_for_ip(ip):
    if FailedLoginCountByIP.query.filter_by(ip=ip).first():
        latest_failed_login_count = dao_get_latest_failed_login_by_ip(ip).failed_login_count
        data = FailedLoginCountByIP(
            ip=ip,
            failed_login_count=latest_failed_login_count + 1,
            attempted_at=datetime.datetime.now(),
        )
    else:
        data = FailedLoginCountByIP(
            ip=ip,
            failed_login_count=1,
            attempted_at=datetime.datetime.now(),
        )
    db.session.add(data)
    db.session.commit()
    return FailedLoginCountByIP.query.filter_by(ip=ip).first()


def dao_get_latest_failed_login_by_ip(ip):
    return FailedLoginCountByIP.query.filter_by(ip=ip).order_by(desc(FailedLoginCountByIP.attempted_at)).first() or None
