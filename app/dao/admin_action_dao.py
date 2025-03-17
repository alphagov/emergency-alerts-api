from emergency_alerts_utils.admin_action import ADMIN_STATUS_PENDING

from app.models import AdminAction


def dao_get_pending_admin_actions() -> list[AdminAction]:
    return AdminAction.query.filter(AdminAction.status == ADMIN_STATUS_PENDING).order_by(AdminAction.created_at)


def dao_get_admin_action_by_id(action_id: str) -> AdminAction:
    return AdminAction.query.filter(AdminAction.id == action_id).one()


def dao_get_all_admin_actions_by_user_id(user_id) -> list[AdminAction]:
    return AdminAction.query.filter_by(created_by_id=user_id).all()


def dao_delete_admin_action_by_id(action_id):
    """Delete an admin action - not just reject it (for tests)"""
    return AdminAction.query.filter_by(id=action_id).delete()
