import logging

from dramatiq.actor import Actor
from dramatiq.middleware import Middleware

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
