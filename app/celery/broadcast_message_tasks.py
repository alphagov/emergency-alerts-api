import boto3

from botocore.exceptions import ClientError
from datetime import datetime
from flask import current_app
from os import environ as env

from app import cbc_proxy_client, notify_celery
from app.clients.cbc_proxy import CBCProxyRetryableException
from app.config import QueueNames, TaskNames
from app.dao.broadcast_message_dao import (
    create_broadcast_provider_message,
    dao_get_broadcast_event_by_id,
    update_broadcast_provider_message_status,
)
from app.models import (
    BroadcastEventMessageType,
    BroadcastProvider,
    BroadcastProviderMessageStatus,
)
from app.utils import format_sequential_number


class BroadcastIntegrityError(Exception):
    pass


sns = boto3.resource('sns')


def get_retry_delay(retry_count):
    """
    Given a count of retries so far, return a delay for the next one.
    `retry_count` should be 0 the first time a task fails.
    """
    # TODO: replace with celery's built in exponential backoff

    # 2 to the power of x. 1, 2, 4, 8, 16, 32, ...
    delay = 2**retry_count
    # never wait longer than 4 minutes
    return min(delay, 240)


def check_event_is_authorised_to_be_sent(broadcast_event, provider):
    if not broadcast_event.service.active:
        raise BroadcastIntegrityError(
            f"Cannot send broadcast_event {broadcast_event.id} " + f"to provider {provider}: the service is suspended"
        )

    if broadcast_event.service.restricted:
        raise BroadcastIntegrityError(
            f"Cannot send broadcast_event {broadcast_event.id} " + f"to provider {provider}: the service is not live"
        )

    if broadcast_event.broadcast_message.stubbed:
        raise BroadcastIntegrityError(
            f"Cannot send broadcast_event {broadcast_event.id} "
            + f"to provider {provider}: the broadcast message is stubbed"
        )


def check_event_makes_sense_in_sequence(broadcast_event, provider):
    """
    If any previous event hasn't sent yet for that provider, then we shouldn't send the current event. Instead, fail and
    raise a zendesk ticket - so that a notify team member can assess the state of the previous messages, and if
    necessary, can replay the `send_broadcast_provider_message` task if the previous message has now been sent.

    Note: This is called before the new broadcast_provider_message is created.

    # Help, I've come across this code following a pagerduty alert, what should I do?

    1. Find the failing broadcast_provider_message associated with the previous event that caused this to trip.
    2. If that provider message is still failing to send, fix the issue causing that. The task to send that previous
       message might still be retrying in the background - look for logs related to that task.
    3. If that provider message has sent succesfully, you might need to send this task off depending on context. This
       might not always be true though, for example, it may not be necessary to send a cancel if the original alert has
       already expired.
    4. If you need to re-send this task off again, you'll need to run the following command on paas:
       `send_broadcast_provider_message.apply_async(args=(broadcast_event_id, provider), queue=QueueNames.BROADCASTS)`
    """
    current_provider_message = broadcast_event.get_provider_message(provider)
    # if this is the first time a task is being executed, it won't have a provider message yet
    if current_provider_message and current_provider_message.status != BroadcastProviderMessageStatus.SENDING:
        raise BroadcastIntegrityError(
            f"Cannot send broadcast_event {broadcast_event.id} "
            + f"to provider {provider}: "
            + f"It is in status {current_provider_message.status}"
        )

    if broadcast_event.transmitted_finishes_at < datetime.utcnow():
        raise BroadcastIntegrityError(
            f"Cannot send broadcast_event {broadcast_event.id} "
            + f"to provider {provider}: "
            + f"The expiry time of {broadcast_event.transmitted_finishes_at} has already passed"
        )

    # get events sorted from earliest to latest
    events = sorted(broadcast_event.broadcast_message.events, key=lambda x: x.sent_at)

    for prev_event in events:
        if prev_event.id != broadcast_event.id and prev_event.sent_at < broadcast_event.sent_at:
            # get the record from when that event was sent to the same provider
            prev_provider_message = prev_event.get_provider_message(provider)

            # the previous message hasn't even got round to running `send_broadcast_provider_message` yet.
            if not prev_provider_message:
                raise BroadcastIntegrityError(
                    f"Cannot send {broadcast_event.id}. Previous event {prev_event.id} "
                    + f"(type {prev_event.message_type}) has no provider_message for provider {provider} yet.\n"
                    + "You must ensure that the other event sends succesfully, then manually kick off this event "
                    + "again by re-running send_broadcast_provider_message for this event and provider."
                )

            # if there's a previous message that has started but not finished sending (whether it fatally errored or is
            # currently retrying)
            if prev_provider_message.status != BroadcastProviderMessageStatus.ACK:
                raise BroadcastIntegrityError(
                    f"Cannot send {broadcast_event.id}. Previous event {prev_event.id} "
                    + f"(type {prev_event.message_type}) has not finished sending to provider {provider} yet.\n"
                    + f'It is currently in status "{prev_provider_message.status}".\n'
                    + "You must ensure that the other event sends succesfully, then manually kick off this event "
                    + "again by re-running send_broadcast_provider_message for this event and provider."
                )


@notify_celery.task(name="send-broadcast-event")
def send_broadcast_event(broadcast_event_id):
    broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)

    topic_name = env.get("GOVUK_ALERTS_SNS_PUBLISH_TOPIC", "test-topic-123123123123123.fifo")
    message = env.get("GOVUK_ALERTS_PUBLISH_MSG", "govuk-alerts-publish-msg")

    # create_topic() is idempotent, so if the requester already owns a topic with the
    # specified name, that topic's ARN is returned without creating a new topic.
    try:
        topic = sns.create_topic(Name=topic_name)
        response = topic.publish(Message=message)
        messageId = response['MessageId']
    except ClientError:
        current_app.logger.exception(f'Could not publish message {messageId} to the topic {topic.arn}.')

    for provider in broadcast_event.service.get_available_broadcast_providers():
        send_broadcast_provider_message.apply_async(
            kwargs={"broadcast_event_id": broadcast_event_id, "provider": provider}, queue=QueueNames.BROADCASTS
        )


# max_retries=None: retry forever
@notify_celery.task(bind=True, name="send-broadcast-provider-message", max_retries=None)
def send_broadcast_provider_message(self, broadcast_event_id, provider):
    if not current_app.config["CBC_PROXY_ENABLED"]:
        current_app.logger.info(
            "CBC Proxy disabled, not sending broadcast_provider_message for "
            f"broadcast_event_id {broadcast_event_id} with provider {provider}"
        )
        return

    broadcast_event = dao_get_broadcast_event_by_id(broadcast_event_id)

    check_event_is_authorised_to_be_sent(broadcast_event, provider)
    check_event_makes_sense_in_sequence(broadcast_event, provider)

    # the broadcast_provider_message may already exist if we retried previously
    broadcast_provider_message = broadcast_event.get_provider_message(provider)
    if broadcast_provider_message is None:
        broadcast_provider_message = create_broadcast_provider_message(broadcast_event, provider)

    formatted_message_number = None
    if provider == BroadcastProvider.VODAFONE:
        formatted_message_number = format_sequential_number(broadcast_provider_message.message_number)

    current_app.logger.info(
        f"Invoking cbc proxy to send broadcast_provider_message with ID of {broadcast_provider_message.id} "
        f"and broadcast_event ID of {broadcast_event_id} "
        f"msgType {broadcast_event.message_type}"
    )

    areas = [{"polygon": polygon} for polygon in broadcast_event.transmitted_areas["simple_polygons"]]

    cbc_proxy_provider_client = cbc_proxy_client.get_proxy(provider)

    try:
        if broadcast_event.message_type == BroadcastEventMessageType.ALERT:
            cbc_proxy_provider_client.create_and_send_broadcast(
                identifier=str(broadcast_provider_message.id),
                message_number=formatted_message_number,
                headline="GOV.UK Emergency Alert",
                description=broadcast_event.transmitted_content["body"],
                areas=areas,
                sent=broadcast_event.sent_at_as_cap_datetime_string,
                expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
                channel=broadcast_event.service.broadcast_channel,
            )
        elif broadcast_event.message_type == BroadcastEventMessageType.UPDATE:
            cbc_proxy_provider_client.update_and_send_broadcast(
                identifier=str(broadcast_provider_message.id),
                message_number=formatted_message_number,
                headline="GOV.UK Emergency Alert",
                description=broadcast_event.transmitted_content["body"],
                areas=areas,
                previous_provider_messages=broadcast_event.get_earlier_provider_messages(provider),
                sent=broadcast_event.sent_at_as_cap_datetime_string,
                expires=broadcast_event.transmitted_finishes_at_as_cap_datetime_string,
                # We think an alert update should always go out on the same channel that created the alert
                # We recognise there is a small risk with this code here that if the services channel was
                # changed between an alert being sent out and then updated, then something might go wrong
                # but we are relying on service channels changing almost never, and not mid incident
                # We may consider in the future, changing this such that we store the channel a broadcast was
                # sent on on the broadcast message itself and pick the value from there instead of the service
                channel=broadcast_event.service.broadcast_channel,
            )
        elif broadcast_event.message_type == BroadcastEventMessageType.CANCEL:
            cbc_proxy_provider_client.cancel_broadcast(
                identifier=str(broadcast_provider_message.id),
                message_number=formatted_message_number,
                previous_provider_messages=broadcast_event.get_earlier_provider_messages(provider),
                sent=broadcast_event.sent_at_as_cap_datetime_string,
            )
    except CBCProxyRetryableException as exc:
        delay = get_retry_delay(self.request.retries)
        current_app.logger.exception(
            f"Retrying send_broadcast_provider_message for broadcast event {broadcast_event_id}, "
            f"provider message {broadcast_provider_message.id}, provider {provider} in {delay} seconds"
        )

        self.retry(
            exc=exc,
            countdown=delay,
            queue=QueueNames.BROADCASTS,
        )

    update_broadcast_provider_message_status(broadcast_provider_message, status=BroadcastProviderMessageStatus.ACK)


@notify_celery.task(name="trigger-link-test")
def trigger_link_test(provider):
    cbc_proxy_client.get_proxy(provider).send_link_test()
