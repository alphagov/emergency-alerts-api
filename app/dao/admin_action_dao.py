from datetime import datetime, timezone

from emergency_alerts_utils.admin_action import (
    ADMIN_ELEVATE_USER,
    ADMIN_ELEVATION_ACTION_TIMEOUT,
    ADMIN_STATUS_INVALIDATED,
    ADMIN_STATUS_PENDING,
)

from app.dao.dao_utils import autocommit
from app.models import AdminAction


def dao_get_pending_valid_admin_actions() -> list[AdminAction]:
    """Gets all the pending admin actions, automatically invalidating any that have expired"""
    all_pending = dao_get_pending_admin_actions()
    valid_pending = []

    elevation_deadline = datetime.now(timezone.utc).replace(tzinfo=None) - ADMIN_ELEVATION_ACTION_TIMEOUT

    for pending in all_pending:
        if pending.action_type == ADMIN_ELEVATE_USER:
            if pending.created_at <= elevation_deadline:
                # Has expired, invalidate it and don't return it
                dao_invalidate_admin_action_by_id(pending.id)
                continue
        # TODO: We could later invalidate things like invites for deleted services, etc
        valid_pending.append(pending)

    return valid_pending


def dao_get_pending_admin_actions() -> list[AdminAction]:
    """Note: You probably want the dao_get_pending_valid_admin_actions method"""
    return AdminAction.query.filter(AdminAction.status == ADMIN_STATUS_PENDING).order_by(AdminAction.created_at)


def dao_get_admin_action_by_id(action_id: str) -> AdminAction:
    return AdminAction.query.filter(AdminAction.id == action_id).one()


def dao_get_all_admin_actions_by_user_id(user_id) -> list[AdminAction]:
    return AdminAction.query.filter_by(created_by_id=user_id).all()


@autocommit
def dao_invalidate_admin_action_by_id(action_id):
    AdminAction.query.filter(AdminAction.id == action_id).update({AdminAction.status: ADMIN_STATUS_INVALIDATED})


@autocommit
def dao_delete_admin_action_by_id(action_id):
    """Delete an admin action - not just reject it (for tests)"""
    return AdminAction.query.filter(AdminAction.id == action_id).delete()
