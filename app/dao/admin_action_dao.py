from app.models import ADMIN_STATUS_PENDING, AdminAction


def dao_get_pending_admin_actions() -> list[AdminAction]:
    return AdminAction.query.filter(AdminAction.status == ADMIN_STATUS_PENDING).order_by(AdminAction.created_at)
