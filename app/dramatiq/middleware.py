import logging

from dramatiq.actor import Actor
from dramatiq.middleware import Middleware
from dramatiq_sqs.broker import _SQSMessage

logger = logging.getLogger(__name__)


class ActorQueuePrefixMiddleware(Middleware):
    """
    Prefix the queue names of actors with a given prefix
    """

    actor_options = {"original_queue_name"}

    def __init__(self, prefix: str = None):
        self.prefix = prefix
        logger.debug("Prefixing queue names with: %s", prefix)

    def before_declare_actor(self, broker, actor: Actor):
        queue_name = actor.queue_name

        # We don't want registering an actor twice to prefix twice
        if "original_queue_name" in actor.options:
            queue_name = actor.options["original_queue_name"]
        actor.options["original_queue_name"] = queue_name

        new_queue_name = self.prefix + queue_name
        logger.debug("Prefixed queue name for actor %s: %s -> %s", actor.actor_name, actor.queue_name, new_queue_name)
        actor.queue_name = new_queue_name


class SqsRetryMiddleware(Middleware):
    """
    This is a homebrew alternative to Dramatiq's Retries middleware, taking consideration
    of SQS' re-delivery behaviour and that re-queuing a message with edited contents counts as a
    new message to SQS. See https://github.com/Bogdanp/dramatiq_sqs/issues/10#issuecomment-2619630546

    This requires the EasSqsConsumer for its nack behaviour and a DLQ within SQS.

    So:
      - If an actor throws and it's not configured for retry, we just log it as failed and drop it.
      - If an actor throws and it's configured for retry, we fail() the message.
        - For a fail() message, the SqsConsumer will avoid deleting (acknowledging) the message and
          get SQS to redeliver it.

      - After many attempts the SQS queue should DLQ the message - no involvement from the logic here.
    """

    actor_options = {"allow_retry"}

    def before_process_message(self, broker, message: _SQSMessage):
        try:
            receive_count = int(message._sqs_message.attributes["ApproximateReceiveCount"])
            logger.info("Message %s has been received %d times", message._sqs_message.message_id, receive_count)
        except Exception:
            pass

    def after_process_message(self, broker, message: _SQSMessage, *, result=None, exception=None):
        if exception is None:
            return

        actor = broker.get_actor(message.actor_name)

        retry_allowed = actor.options.get("allow_retry")

        if retry_allowed:
            logger.warning(
                "Message %s had an exception but allows retries, failing it so SQS can retry or DLQ it",
                message.message_id,
            )
            message.fail()
        else:
            logger.warning("Message %s had an exception but isn't configured for retries. It will be dropped.")
