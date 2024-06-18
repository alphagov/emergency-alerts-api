from app.models import FailedLoginCountByIP
from app import db


def dao_get_failed_login_counts():
    return FailedLoginCountByIP.query.all()


def dao_create_failed_login_for_ip(ip):
    data = FailedLoginCountByIP(ip=ip, failed_login_count=1)
    db.session.add(data)
    db.session.commit()
    return FailedLoginCountByIP.query.filter_by(ip=ip).first()


def dao_get_failed_login_counts_by_ip(ip):
    if not FailedLoginCountByIP.query.filter_by(ip=ip).first():
        dao_create_failed_login_for_ip(ip)
    return FailedLoginCountByIP.query.filter_by(ip=ip).first()


def dao_increment_failed_login_counts_by_ip(failed_login):
    failed_login.failed_login_count += 1
    db.session.add(failed_login)
    db.session.commit()
    return FailedLoginCountByIP.query.filter_by(ip=failed_login.ip).first()


def dao_reset_failed_login_counts_by_ip(failed_login):
    failed_login.failed_login_count = 0
    db.session.add(failed_login)
    db.session.commit()
    return FailedLoginCountByIP.query.filter_by(ip=failed_login.ip).first()
