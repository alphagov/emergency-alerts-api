from datetime import datetime, timezone

from app import create_uuid, db
from app.dao.dao_utils import autocommit, version_class
from app.models import ServiceCallbackApi


@autocommit
@version_class(ServiceCallbackApi)
def save_service_callback_api(service_callback_api):
    service_callback_api.id = create_uuid()
    service_callback_api.created_at = datetime.now(timezone.utc)
    db.session.add(service_callback_api)


@autocommit
@version_class(ServiceCallbackApi)
def reset_service_callback_api(service_callback_api, updated_by_id, url=None, bearer_token=None):
    if url:
        service_callback_api.url = url
    if bearer_token:
        service_callback_api.bearer_token = bearer_token
    service_callback_api.updated_by_id = updated_by_id
    service_callback_api.updated_at = datetime.now(timezone.utc)

    db.session.add(service_callback_api)


def get_service_callback_api(service_callback_api_id, service_id):
    return ServiceCallbackApi.query.filter_by(id=service_callback_api_id, service_id=service_id).first()


@autocommit
def delete_service_callback_api(service_callback_api):
    db.session.delete(service_callback_api)
