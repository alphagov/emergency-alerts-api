from datetime import datetime, timezone

from flask import current_app

from app import db
from app.dao.dao_utils import autocommit, version_class
from app.models import (
    BROADCAST_TYPE,
    EMAIL_AUTH_TYPE,
    INVITE_PENDING,
    VIEW_ACTIVITY,
    ApiKey,
    InvitedUser,
    Organisation,
    Permission,
    Service,
    ServiceBroadcastProviders,
    ServiceBroadcastSettings,
    ServicePermission,
)


@autocommit
@version_class(Service)
def set_broadcast_service_type(service, service_mode, broadcast_channel, provider_restriction):
    insert_or_update_service_broadcast_settings(service, channel=broadcast_channel)
    set_service_broadcast_providers(service, provider_restriction)

    # Remove all permissions and add broadcast permission
    if not service.has_permission(BROADCAST_TYPE):
        service_permission = ServicePermission(service_id=service.id, permission=BROADCAST_TYPE)
        db.session.add(service_permission)

    ServicePermission.query.filter(
        ServicePermission.service_id == service.id,
        ServicePermission.permission != BROADCAST_TYPE,
        # Email auth is an exception to the other service permissions (which relate to what type
        # of notifications a service can send) where a broadcast service is allowed to have the
        # email auth permission (but doesn't have to)
        ServicePermission.permission != EMAIL_AUTH_TYPE,
    ).delete()

    # Refresh the service object as it has references to the service permissions but we don't yet
    # want to commit the permission changes incase all of this needs to rollback
    db.session.refresh(service)

    # Set service into training mode or live mode
    if service_mode == "live":
        if service.restricted:
            # Only update the go live at timestamp if this if moving from training mode
            # to live mode, not if it's moving from one type of live mode service to another
            service.go_live_at = datetime.now(timezone.utc)

            # Remove all user permissions apart from view_activity for the service users and invited users
            # only if the service is moving from training mode to live mode
            Permission.query.filter(
                Permission.service_id == service.id, Permission.permission != VIEW_ACTIVITY
            ).delete()
            InvitedUser.query.filter_by(service_id=service.id, status=INVITE_PENDING).update(
                {"permissions": VIEW_ACTIVITY}
            )

        service.restricted = False
    else:
        service.restricted = True
        service.go_live_at = None

    # Revoke any API keys to avoid a regular API key being used to send alerts
    ApiKey.query.filter_by(
        service_id=service.id,
        expiry_date=None,
    ).update({ApiKey.expiry_date: datetime.now(timezone.utc)})

    # Add service to organisation
    organisation = Organisation.query.filter_by(id=current_app.config["BROADCAST_ORGANISATION_ID"]).one()
    service.organisation_id = organisation.id
    service.organisation_type = organisation.organisation_type
    service.crown = organisation.crown

    db.session.add(service)


def insert_or_update_service_broadcast_settings(service, channel):
    if not service.service_broadcast_settings:
        settings = ServiceBroadcastSettings()
        settings.service = service
        settings.channel = channel
        settings.provider = "deprecated"
        db.session.add(settings)
    else:
        service.service_broadcast_settings.channel = channel
        service.service_broadcast_settings.provider = "deprecated"
        db.session.add(service.service_broadcast_settings)


def set_service_broadcast_providers(service, provider_restriction):
    """ "
    Remove old providers and apply new provider list
    """
    ServiceBroadcastProviders.query.filter(
        ServiceBroadcastProviders.service_id == service.id,
    ).delete()

    for provider in provider_restriction:
        providers = ServiceBroadcastProviders()
        providers.service_id = service.id
        providers.provider = provider
        db.session.add(providers)


def get_service_broadcast_providers(service_id):
    query = ServiceBroadcastProviders.query.filter_by(service_id=service_id)
    return query.all()
