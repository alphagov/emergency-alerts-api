import logging
import signal

from app.dramatiq_dlq.dlq_watcher import DlqWatcher
from application import application

logger = logging.getLogger(__name__)


if "__main__" == __name__:
    with application.app_context():
        dlq_watcher = DlqWatcher()

        def stop(*args):
            logger.info("Received signal to terminate: %s", args)
            dlq_watcher.stop = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)

        dlq_watcher.run()
