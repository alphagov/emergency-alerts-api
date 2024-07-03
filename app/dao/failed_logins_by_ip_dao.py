import datetime

from sqlalchemy import desc

from app import db
from app.models import FailedLoginCountByIP


def dao_get_failed_logins():
    return FailedLoginCountByIP.query.all()


def dao_create_failed_login_for_ip(ip):
    data = FailedLoginCountByIP(
        ip=ip,
        attempted_at=datetime.datetime.now(),
    )
    db.session.add(data)
    db.session.commit()
    return FailedLoginCountByIP.query.filter_by(ip=ip).first()


def dao_get_latest_failed_login_by_ip(ip):
    return FailedLoginCountByIP.query.filter_by(ip=ip).order_by(desc(FailedLoginCountByIP.attempted_at)).first() or None


def dao_get_count_of_all_failed_logins_for_ip(ip):
    return FailedLoginCountByIP.query.filter_by(ip=ip).count()
