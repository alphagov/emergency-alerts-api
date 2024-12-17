import itertools

from emergency_alerts_utils.validation import allowed_to_send_to

from app.dao.services_dao import dao_fetch_service_by_id
from app.models import KEY_TYPE_NORMAL, KEY_TYPE_TEAM, KEY_TYPE_TEST


def get_recipients_from_request(request_json, key, type):
    return [(type, recipient) for recipient in request_json.get(key)]


def service_allowed_to_send_to(recipient, service, key_type, allow_guest_list_recipients=True):
    if key_type == KEY_TYPE_TEST:
        return True

    if key_type == KEY_TYPE_NORMAL and not service.restricted:
        return True

    # Revert back to the ORM model here so we can get some things which
    # aren’t in the serialised model
    service = dao_fetch_service_by_id(service.id)

    team_members = itertools.chain.from_iterable([user.mobile_number, user.email_address] for user in service.users)
    guest_list_members = [member.recipient for member in service.guest_list if allow_guest_list_recipients]

    if (key_type == KEY_TYPE_NORMAL and service.restricted) or (key_type == KEY_TYPE_TEAM):
        return allowed_to_send_to(recipient, itertools.chain(team_members, guest_list_members))
