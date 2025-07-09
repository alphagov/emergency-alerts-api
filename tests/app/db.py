import uuid
from datetime import datetime, timedelta, timezone

import pytest
from emergency_alerts_utils.api_key import KEY_TYPE_NORMAL

from app import db
from app.dao.invited_org_user_dao import save_invited_org_user
from app.dao.invited_user_dao import save_invited_user
from app.dao.organisation_dao import dao_create_organisation
from app.dao.permissions_dao import permission_dao
from app.dao.service_callback_api_dao import save_service_callback_api
from app.dao.service_inbound_api_dao import save_service_inbound_api
from app.dao.service_permissions_dao import dao_add_service_permission
from app.dao.services_dao import dao_add_user_to_service, dao_create_service
from app.dao.templates_dao import dao_create_template, dao_update_template
from app.dao.users_dao import save_model_user
from app.models import (
    BROADCAST_TYPE,
    EMAIL_TYPE,
    AdminAction,
    ApiKey,
    BroadcastEvent,
    BroadcastMessage,
    BroadcastMessageEditReasons,
    BroadcastMessageHistory,
    BroadcastProvider,
    BroadcastProviderMessage,
    BroadcastProviderMessageNumber,
    BroadcastStatusType,
    Domain,
    FailedLogin,
    FeatureToggle,
    InvitedOrganisationUser,
    InvitedUser,
    Organisation,
    Permission,
    Service,
    ServiceCallbackApi,
    ServiceInboundApi,
    ServicePermission,
    Template,
    TemplateFolder,
    User,
    WebauthnCredential,
)


def create_user(*, mobile_number="+447712345678", email=None, state="active", id_=None, name="Test User"):
    data = {
        "id": id_ or uuid.uuid4(),
        "name": name,
        "email_address": email or f"{uuid.uuid4()}@digital.cabinet-office.gov.uk",
        "password": "password",
        "mobile_number": mobile_number,
        "state": state,
    }
    user = User.query.filter_by(email_address=email).first()
    if not user:
        user = User(**data)
    save_model_user(user, validated_email_access=True)
    return user


def create_permissions(user, service, *permissions):
    permissions = [Permission(service_id=service.id, user_id=user.id, permission=p) for p in permissions]

    permission_dao.set_user_service_permission(user, service, permissions, _commit=True)


def create_service(
    user=None,
    service_name="Sample service",
    service_id=None,
    restricted=False,
    service_permissions=None,
    active=True,
    organisation_type="central",
    check_if_service_exists=False,
    go_live_user=None,
    go_live_at=None,
    crown=True,
    organisation=None,
):
    if check_if_service_exists:
        service = Service.query.filter_by(name=service_name).first()
    if (not check_if_service_exists) or (check_if_service_exists and not service):
        service = Service(
            name=service_name,
            restricted=restricted,
            created_by=user if user else create_user(email="{}@digital.cabinet-office.gov.uk".format(uuid.uuid4())),
            organisation_type=organisation_type,
            organisation=organisation,
            go_live_user=go_live_user,
            go_live_at=go_live_at,
            crown=crown,
        )
        dao_create_service(
            service,
            service.created_by,
            service_id,
            service_permissions=service_permissions,
        )
        service.active = active
    else:
        if user and user not in service.users:
            dao_add_user_to_service(service, user)

    return service


def create_template(
    service,
    template_type=BROADCAST_TYPE,
    template_name=None,
    content="Dear Sir/Madam, Hello. Yours Truly, The Government.",
    archived=False,
    folder=None,
):
    data = {
        "name": template_name or "{} Template Name".format(template_type),
        "template_type": template_type,
        "content": content,
        "service": service,
        "created_by": service.created_by,
        "folder": folder,
    }
    template = Template(**data)
    dao_create_template(template)

    if archived:
        template.archived = archived
        dao_update_template(template)

    return template


def create_service_permission(service_id, permission=EMAIL_TYPE):
    dao_add_service_permission(service_id if service_id else create_service().id, permission)

    service_permissions = ServicePermission.query.all()

    return service_permissions


def create_service_inbound_api(
    service,
    url="https://something.com",
    bearer_token="some_super_secret",
):
    service_inbound_api = ServiceInboundApi(
        service_id=service.id, url=url, bearer_token=bearer_token, updated_by_id=service.users[0].id
    )
    save_service_inbound_api(service_inbound_api)
    return service_inbound_api


def create_service_callback_api(
    service, url="https://something.com", bearer_token="some_super_secret", callback_type="delivery_status"
):
    service_callback_api = ServiceCallbackApi(
        service_id=service.id,
        url=url,
        bearer_token=bearer_token,
        updated_by_id=service.users[0].id,
        callback_type=callback_type,
    )
    save_service_callback_api(service_callback_api)
    return service_callback_api


def create_api_key(service, key_type=KEY_TYPE_NORMAL, key_name=None):
    id_ = uuid.uuid4()

    name = key_name if key_name else "{} api key {}".format(key_type, id_)

    api_key = ApiKey(
        service=service, name=name, created_by=service.created_by, key_type=key_type, id=id_, secret=uuid.uuid4()
    )
    db.session.add(api_key)
    db.session.commit()
    return api_key


def create_domain(domain, organisation_id):
    domain = Domain(domain=domain, organisation_id=organisation_id)

    db.session.add(domain)
    db.session.commit()

    return domain


def create_organisation(
    name="test_org_1",
    active=True,
    organisation_type=None,
    domains=None,
    organisation_id=None,
):
    data = {
        "id": organisation_id,
        "name": name,
        "active": active,
        "organisation_type": organisation_type,
    }
    organisation = Organisation(**data)
    dao_create_organisation(organisation)

    for domain in domains or []:
        create_domain(domain, organisation.id)

    return organisation


def create_invited_org_user(organisation, invited_by, email_address="invite@example.com"):
    invited_org_user = InvitedOrganisationUser(
        email_address=email_address,
        invited_by=invited_by,
        organisation=organisation,
    )
    save_invited_org_user(invited_org_user)
    return invited_org_user


def ses_notification_callback():
    return (
        '{\n  "Type" : "Notification",\n  "MessageId" : "ref1",'
        '\n  "TopicArn" : "arn:aws:sns:eu-west-2:123456789012:testing",'
        '\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",'
        '\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",'
        '\\"source\\":\\"test@test-domain.com\\",'
        '\\"sourceArn\\":\\"arn:aws:ses:eu-west-2:123456789012:identity/testing-notify\\",'
        '\\"sendingAccountId\\":\\"123456789012\\",'
        '\\"messageId\\":\\"ref1\\",'
        '\\"destination\\":[\\"testing@digital.cabinet-office.gov.uk\\"]},'
        '\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",'
        '\\"processingTimeMillis\\":658,'
        '\\"recipients\\":[\\"testing@digital.cabinet-office.gov.uk\\"],'
        '\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",'
        '\\"reportingMTA\\":\\"a6-238.smtp-out.eu-west-2.amazonses.com\\"}}",'
        '\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",'
        '\n  "Signature" : "X8d7eTAOZ6wlnrdVVPYanrAlsX0SMPfOzhoTEBnQqYkrNWTqQY91C0f3bxtPdUhUt'
        "OowyPAOkTQ4KnZuzphfhVb2p1MyVYMxNKcBFB05/qaCX99+92fjw4x9LeUOwyGwMv5F0Vkfi5qZCcEw69uVrhYL"
        "VSTFTrzi/yCtru+yFULMQ6UhbY09GwiP6hjxZMVr8aROQy5lLHglqQzOuSZ4KeD85JjifHdKzlx8jjQ+uj+FLzHXPMA"
        'PmPU1JK9kpoHZ1oPshAFgPDpphJe+HwcJ8ezmk+3AEUr3wWli3xF+49y8Z2anASSVp6YI2YP95UT8Rlh3qT3T+V9V8rbSVislxA==",'
        '\n  "SigningCertURL" : "https://sns.eu-west-2.amazonaws.com/SimpleNotificationService-bb750'
        'dd426d95ee9390147a5624348ee.pem",'
        '\n  "UnsubscribeURL" : "https://sns.eu-west-2.amazonaws.com/?Action=Unsubscribe&S'
        'subscriptionArn=arn:aws:sns:eu-west-2:302763885840:preview-emails:d6aad3ef-83d6-4cf3-a470-54e2e75916da"\n}'
    )


def create_invited_user(service=None, to_email_address=None):
    if service is None:
        service = create_service()
    if to_email_address is None:
        to_email_address = "invited_user@digital.gov.uk"

    from_user = service.users[0]

    data = {
        "service": service,
        "email_address": to_email_address,
        "from_user": from_user,
        "permissions": "create_broadcasts,manage_service,manage_api_keys",
        "folder_permissions": [str(uuid.uuid4()), str(uuid.uuid4())],
    }
    invited_user = InvitedUser(**data)
    save_invited_user(invited_user)
    return invited_user


def create_template_folder(service, name="foo", parent=None, users=None):
    tf = TemplateFolder(name=name, service=service, parent=parent)
    if users is not None:
        tf.users = users
    db.session.add(tf)
    db.session.commit()
    return tf


def create_broadcast_message(
    template=None,
    *,
    service=None,  # only used if template is not provided
    created_by=None,
    content=None,
    status=BroadcastStatusType.DRAFT,
    starts_at=None,
    finishes_at=None,
    areas=None,
    stubbed=False,
    cap_event=None,
    created_at=None,  # only used for testing
    reference=None,
    submitted_by=None,
    extra_content=None,
):
    if template:
        service = template.service
        template_id = template.id
        template_version = template.version
        content = template.content
        reference = template.name
    elif content:
        template_id = None
        template_version = None
        content = content
    else:
        pytest.fail("Provide template or content")

    broadcast_message = BroadcastMessage(
        service_id=service.id,
        template_id=template_id,
        template_version=template_version,
        # personalisation=personalisation,
        status=status,
        starts_at=starts_at,
        finishes_at=finishes_at,
        created_by_id=created_by.id if created_by else service.created_by_id,
        areas=areas or {"ids": [], "simple_polygons": []},
        content=content,
        stubbed=stubbed,
        cap_event=cap_event,
        created_at=created_at,
        reference=reference,
        submitted_by=submitted_by,
        submitted_at=datetime.now(),
        extra_content=extra_content,
    )
    db.session.add(broadcast_message)
    db.session.commit()
    return broadcast_message


def create_broadcast_event(
    broadcast_message,
    sent_at=None,
    message_type="alert",
    transmitted_content=None,
    transmitted_areas=None,
    transmitted_sender=None,
    transmitted_starts_at=None,
    transmitted_finishes_at=None,
):
    b_e = BroadcastEvent(
        service=broadcast_message.service,
        broadcast_message=broadcast_message,
        sent_at=sent_at or datetime.now(timezone.utc),
        message_type=message_type,
        transmitted_content=transmitted_content or {"body": "this is an emergency broadcast message"},
        transmitted_areas=transmitted_areas or broadcast_message.areas,
        transmitted_sender=transmitted_sender or "www.notifications.service.gov.uk",
        transmitted_starts_at=transmitted_starts_at,
        transmitted_finishes_at=transmitted_finishes_at or datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.session.add(b_e)
    db.session.commit()
    return b_e


def create_broadcast_provider_message(broadcast_event, provider, status="sending"):
    broadcast_provider_message_id = uuid.uuid4()
    provider_message = BroadcastProviderMessage(
        id=broadcast_provider_message_id,
        broadcast_event=broadcast_event,
        provider=provider,
        status=status,
    )
    db.session.add(provider_message)
    db.session.commit()

    provider_message_number = None
    if provider == BroadcastProvider.VODAFONE:
        provider_message_number = BroadcastProviderMessageNumber(
            broadcast_provider_message_id=broadcast_provider_message_id
        )
        db.session.add(provider_message_number)
        db.session.commit()
    return provider_message


def create_webauthn_credential(
    user,
    name="my key",
    *,
    credential_data="ABC123",
    registration_response="DEF456",
):
    webauthn_credential = WebauthnCredential(
        user=user, name=name, credential_data=credential_data, registration_response=registration_response
    )

    db.session.add(webauthn_credential)
    db.session.commit()
    return webauthn_credential


def create_feature_toggle(name="feature_toggle", is_enabled=True, display_html=None):
    feature_toggle = FeatureToggle(name=name, is_enabled=is_enabled, display_html=display_html)

    db.session.add(feature_toggle)
    db.session.commit()
    return feature_toggle


def create_failed_login(ip, attempted_at):
    failed_login = FailedLogin(ip=ip, attempted_at=attempted_at)
    db.session.add(failed_login)
    db.session.commit()
    return failed_login


def create_admin_action(service_id, created_by, action_type, action_data, status):
    action = AdminAction(
        service_id=service_id, created_by_id=created_by, action_type=action_type, action_data=action_data, status=status
    )

    db.session.add(action)
    db.session.commit()
    return action


def create_broadcast_message_version(
    *,
    id=None,
    broadcast_message_id=None,
    created_by=None,
    content="Test Broadcast Content",
    areas=None,
    created_at=None,
    reference="Test Broadcast Reference",
    created_by_id=None,
    service_id=None,
    duration=None,
):
    broadcast_message_version = BroadcastMessageHistory(
        id=id,
        broadcast_message_id=broadcast_message_id,
        service_id=service_id,
        created_by_id=created_by_id,
        areas=areas or {"ids": [], "simple_polygons": []},
        content=content,
        created_at=created_at,
        reference=reference,
        duration=duration,
    )
    db.session.add(broadcast_message_version)
    db.session.commit()
    return broadcast_message_version


def create_broadcast_message_edit_reason(broadcast_message_id, service_id, edit_reason, user_id_1, user_id_2):
    broadcast_message_edit_reason = BroadcastMessageEditReasons(
        id=uuid.uuid4(),
        broadcast_message_id=broadcast_message_id,
        created_at=datetime.now(),
        service_id=service_id,
        created_by_id=user_id_1,
        edit_reason=edit_reason,
        submitted_by_id=user_id_2,
        submitted_at=datetime.now(),
    )
    db.session.add(broadcast_message_edit_reason)
    db.session.commit()
    return broadcast_message_edit_reason
