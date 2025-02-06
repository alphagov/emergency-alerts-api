from datetime import datetime, timedelta, timezone

from sqlalchemy import desc

from app import db
from app.models import InvitedUser


def save_invited_user(invited_user):
    db.session.add(invited_user)
    db.session.commit()


def get_invited_user_by_service_and_id(service_id, invited_user_id):
    return InvitedUser.query.filter_by(service_id=service_id, id=invited_user_id).one()


def get_invited_user_by_id(invited_user_id):
    return InvitedUser.query.filter_by(id=invited_user_id).one()


def get_invited_user_by_email(email):
    return InvitedUser.query.filter_by(email_address=email).order_by(desc(InvitedUser.created_at)).first()


def get_invited_users_for_service(service_id):
    return InvitedUser.query.filter_by(service_id=service_id).all()


def delete_invitations_created_more_than_two_days_ago():
    deleted = (
        db.session.query(InvitedUser)
        .filter(InvitedUser.created_at <= datetime.now(timezone.utc) - timedelta(days=2))
        .delete()
    )
    db.session.commit()
    return deleted


def delete_invitations_sent_by_user(user_id):
    db.session.query(InvitedUser).filter_by(user_id=user_id).delete()
    db.session.commit()
