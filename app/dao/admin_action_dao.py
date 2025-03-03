from emergency_alerts_utils.admin_action import ADMIN_STATUS_PENDING

from app.models import AdminAction


def dao_get_pending_admin_actions() -> list[AdminAction]:
    return AdminAction.query.filter(AdminAction.status == ADMIN_STATUS_PENDING).order_by(AdminAction.created_at)


def dao_get_admin_action_by_id(action_id: str) -> AdminAction:
    return AdminAction.query.filter(AdminAction.id == action_id).one()
