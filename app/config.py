import os

from celery.schedules import crontab
from kombu import Exchange, Queue


class QueueNames(object):
    PERIODIC = "periodic-tasks"
    BROADCASTS = "broadcast-tasks"
    GOVUK_ALERTS = "govuk-alerts"


class TaskNames(object):
    PUBLISH_GOVUK_ALERTS = "publish-govuk-alerts"
    TRIGGER_GOVUK_HEALTHCHECK = "trigger-govuk-alerts-healthcheck"


class BroadcastProvider:
    EE = "ee"
    VODAFONE = "vodafone"
    THREE = "three"
    O2 = "o2"

    PROVIDERS = [EE, O2, THREE, VODAFONE]


"""
IMPORTANT NOTES ON CONFIGURING ENVIRONMENT VARIABLES

The HOST variable is used to distinguish between running locally and on the hosted infrastructure (i.e. AWS).
This variable can therefore take one of the following values:

HOST = [ local | hosted | test ]

"local" indicates that the service will be configured for running on a local machine. "hosted" is intended
for use when the service is running on the AWS-hosted infrastructure. "test" provides a special set of
configuration values that may be used by the unit, integration and functional tests.

The environment variable ENVIRONMENT is used to tell the service which set of config values to take up,
and can be set to one of the following values:

ENVIRONMENT = [ local | development | preview | staging | production ]

A value of "local" indicates that the service will be running on the development machine. A value corresponding
to any of the others in the above set maps directly to the name of the environment hosted in AWS.

The development environment hosted on AWS will now configure the above variables as follows:
HOST=hosted & ENVIRONMENT=development

"""


class Config(object):
    # secrets that internal apps, such as the admin app or document download, must use to authenticate with the API
    ADMIN_CLIENT_ID = "notify-admin"
    GOVUK_ALERTS_CLIENT_ID = "govuk-alerts"
    INTERNAL_CLIENT_API_KEYS = {
        ADMIN_CLIENT_ID: [os.environ.get("ADMIN_CLIENT_SECRET")],
        GOVUK_ALERTS_CLIENT_ID: ["govuk-alerts-secret-key"],
    }
    SECRET_KEY = os.environ.get("SECRET_KEY")
    DANGEROUS_SALT = os.environ.get("DANGEROUS_SALT")

    ENCRYPTION_SECRET_KEY = os.environ.get("ENCRYPTION_SECRET_KEY")
    ENCRYPTION_DANGEROUS_SALT = os.environ.get("ENCRYPTION_DANGEROUS_SALT")

    ADMIN_BASE_URL = "http://localhost:6012"
    API_HOST_NAME = "http://localhost:6011"
    API_RATE_LIMIT_ENABLED = True

    CBC_ACCOUNT_NUMBER = os.getenv("CBC_ACCOUNT_NUMBER")
    CBC_PROXY_ENABLED = True
    ENABLED_CBCS = {BroadcastProvider.EE, BroadcastProvider.THREE, BroadcastProvider.O2, BroadcastProvider.VODAFONE}

    if os.environ.get("MASTER_USERNAME"):
        print("Using master credentials for db connection")
        SQLALCHEMY_DATABASE_URI = "postgresql://{user}:{password}@{host}:{port}/{database}".format(
            user=os.environ.get("MASTER_USERNAME", "root"),
            password=os.environ.get("MASTER_PASSWORD"),
            host=os.environ.get("RDS_HOST", "localhost"),
            port=os.environ.get("RDS_PORT", 5432),
            database=os.environ.get("DATABASE", "emergency_alerts"),
        )
    else:
        print("Using no credentials for db connection")
        SQLALCHEMY_DATABASE_URI = "postgresql://{user}@{host}:{port}/{database}".format(
            user=os.environ.get("RDS_USER", "root"),
            host=os.environ.get("RDS_HOST", "localhost"),
            port=os.environ.get("RDS_PORT", 5432),
            database=os.environ.get("DATABASE", "emergency_alerts"),
        )

    if os.environ.get("SQLALCHEMY_LOCAL_OVERRIDE"):
        print("Overriding db connection string for local running")
        SQLALCHEMY_DATABASE_URI = os.environ.get("SQLALCHEMY_LOCAL_OVERRIDE")

    # Prefix to identify queues in SQS
    NOTIFICATION_QUEUE_PREFIX = (
        f"{os.getenv('NOTIFICATION_QUEUE_PREFIX')}-"
        if os.getenv("NOTIFICATION_QUEUE_PREFIX")
        else f"{os.getenv('ENVIRONMENT')}-"
    )

    ZENDESK_API_KEY = os.environ.get("ZENDESK_API_KEY")
    REPORTS_SLACK_WEBHOOK_URL = os.environ.get("REPORTS_SLACK_WEBHOOK_URL")

    # Logging
    DEBUG = True
    SQLALCHEMY_ECHO = False

    HOST = "local"
    AWS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
    INVITATION_EXPIRATION_DAYS = 2
    EAS_APP_NAME = "api"
    NOTIFY_EMAIL_DOMAIN = "notify.tools"
    SQLALCHEMY_POOL_SIZE = int(os.environ.get("SQLALCHEMY_POOL_SIZE", 5))
    SQLALCHEMY_POOL_TIMEOUT = 30
    SQLALCHEMY_POOL_RECYCLE = 300
    SQLALCHEMY_STATEMENT_TIMEOUT = 1200
    PAGE_SIZE = 50
    API_PAGE_SIZE = 250
    TEST_MESSAGE_FILENAME = "Test message"
    ONE_OFF_MESSAGE_FILENAME = "Report"
    MAX_VERIFY_CODE_COUNT = 5
    MAX_FAILED_LOGIN_COUNT = 10
    MIN_ENTROPY_THRESHOLD = 70

    CHECK_PROXY_HEADER = False

    NOTIFY_SERVICE_ID = "d6aa2c68-a2d9-4437-ab19-3ae8eb202553"
    NOTIFY_USER_ID = "6af522d0-2915-4e52-83a3-3690455a5fe6"
    INVITATION_EMAIL_TEMPLATE_ID = "ad68eafb-0926-4cd4-9dc4-be4aa3393b1b"
    BROADCAST_INVITATION_EMAIL_TEMPLATE_ID = "825c5863-0875-416c-8c55-6238e37808e7"
    SMS_CODE_TEMPLATE_ID = "a5b3439f-6dc5-46b0-8ea6-769eb9d16289"
    EMAIL_2FA_TEMPLATE_ID = "83d40e06-4500-43b0-b39f-74bc9c5fd7e5"
    NEW_USER_EMAIL_VERIFICATION_TEMPLATE_ID = "0fbfa614-9c02-4ea6-a35a-d1e7b23cdb5c"
    PASSWORD_RESET_TEMPLATE_ID = "758b722a-67d4-4630-8293-dd3908be75e6"
    ALREADY_REGISTERED_EMAIL_TEMPLATE_ID = "e743bbb5-5a79-4006-8e72-570e9de85920"
    CHANGE_EMAIL_CONFIRMATION_TEMPLATE_ID = "41773bfa-86f2-464a-86bf-3828adb486a9"
    SERVICE_NOW_LIVE_TEMPLATE_ID = "9e10c154-d989-4cfe-80ca-481cd09b7251"
    ORGANISATION_INVITATION_EMAIL_TEMPLATE_ID = "8c9c51a0-5842-484d-918f-d9f7d9b8cab9"
    TEAM_MEMBER_EDIT_EMAIL_TEMPLATE_ID = "c5aeab5e-dd4f-431d-b544-ebd944f3c942"
    TEAM_MEMBER_EDIT_MOBILE_TEMPLATE_ID = "c8474c57-6601-47bb-ba67-caacf9716ee1"
    REPLY_TO_EMAIL_ADDRESS_VERIFICATION_TEMPLATE_ID = "3a8a49b6-6d53-412f-b346-cae568a19de9"
    SECURITY_INFO_CHANGE_EMAIL_TEMPLATE_ID = "719a247f-f8b8-46d3-b0f8-c0f44b61d4b8"
    SECURITY_INFO_CHANGE_SMS_TEMPLATE_ID = "b2bfe780-ca4a-45a3-8a03-ba7a64cf0953"
    SECURITY_KEY_CHANGE_EMAIL_TEMPLATE_ID = "43d7b34a-45c5-4d37-96f8-2c3f48d4d0a5"
    NOTIFY_INTERNATIONAL_SMS_SENDER = "07984404008"
    SERVICE = os.environ.get("SERVICE")
    QUEUE_NAME = QueueNames.BROADCASTS if SERVICE == "api" else QueueNames.PERIODIC
    TASK_IMPORTS = "broadcast_message_tasks" if SERVICE == "api" else "scheduled_tasks"

    CELERY = {
        "broker":"sqs://",
        # "broker_url": f"https://sqs.{AWS_REGION}.amazonaws.com",
        "broker_transport": "sqs",
        "broker_transport_options": {
            "region": AWS_REGION,
            # "queue_name_prefix": NOTIFICATION_QUEUE_PREFIX,
            "predefined_queues": {
                QUEUE_NAME: {
                    "url": f"https://sqs.{AWS_REGION}.amazonaws.com/{NOTIFICATION_QUEUE_PREFIX}{QUEUE_NAME}",
                }
            },
            "is_secure": True,
            "task_acks_late": True,
        },
        "timezone": "UTC",
        "imports": [
            f"app.celery.{TASK_IMPORTS}",
        ],
        "worker_max_tasks_per_child": 10,
        "worker_hijack_root_logger": False,
        "task_queues": [Queue(QUEUE_NAME, Exchange("default"), routing_key=QUEUE_NAME)],
        "beat_schedule": {
            "run-health-check": {
                "task": "run-health-check",
                "schedule": crontab(minute="*/1"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            TaskNames.TRIGGER_GOVUK_HEALTHCHECK: {
                "task": TaskNames.TRIGGER_GOVUK_HEALTHCHECK,
                "schedule": crontab(minute="*/1"),
                "options": {"queue": QueueNames.GOVUK_ALERTS},
            },
            "trigger-link-tests": {
                "task": "trigger-link-tests",
                "schedule": crontab(minute="*/15"),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "delete-verify-codes": {
                "task": "delete-verify-codes",
                "schedule": crontab(minute=10),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "delete-invitations": {
                "task": "delete-invitations",
                "schedule": crontab(minute=20),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "auto-expire-broadcast-messages": {
                "task": "auto-expire-broadcast-messages",
                "schedule": crontab(minute=40),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "remove-yesterdays-planned-tests-on-govuk-alerts": {
                "task": "remove-yesterdays-planned-tests-on-govuk-alerts",
                "schedule": crontab(hour=00, minute=00),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "delete-old-records-from-events-table": {
                "task": "delete-old-records-from-events-table",
                "schedule": crontab(hour=3, minute=00),
                "options": {"queue": QueueNames.PERIODIC},
            },
            "validate-functional-test-account-emails": {
                "task": "validate-functional-test-account-emails",
                "schedule": crontab(day_of_month="1"),
                "options": {"queue": QueueNames.PERIODIC},
            },
        },
    }

    FROM_NUMBER = "development"

    STATSD_HOST = os.getenv("STATSD_HOST")
    STATSD_PORT = 8125
    STATSD_ENABLED = bool(STATSD_HOST)

    SENDING_NOTIFICATIONS_TIMEOUT_PERIOD = 259200  # 3 days
    ADMIN_EXTERNAL_URL = "http://127.0.0.1:6012/"

    SIMULATED_EMAIL_ADDRESSES = (
        "simulate-delivered@notifications.service.gov.uk",
        "simulate-delivered-2@notifications.service.gov.uk",
        "simulate-delivered-3@notifications.service.gov.uk",
    )

    ROUTE_SECRET_KEY_1 = os.environ.get("ROUTE_SECRET_KEY_1", "")
    ROUTE_SECRET_KEY_2 = os.environ.get("ROUTE_SECRET_KEY_2", "")

    TEMPLATE_PREVIEW_API_HOST = os.environ.get("TEMPLATE_PREVIEW_API_HOST", "http://localhost:6013")
    TEMPLATE_PREVIEW_API_KEY = os.environ.get("TEMPLATE_PREVIEW_API_KEY", "my-secret-key")

    EAS_EMAIL_REPLY_TO_ID = "591164ac-721d-46e5-b329-fe40f5253241"

    # as defined in api db migration 0331_add_broadcast_org.py
    BROADCAST_ORGANISATION_ID = "38e4bf69-93b0-445d-acee-53ea53fe02df"

    FUNCTIONAL_TESTS_BROADCAST_SERVICE_NAME = "Functional Tests Broadcast Service"
    FUNCTIONAL_TESTS_BROADCAST_SERVICE_ID = "8e1d56fa-12a8-4d00-bed2-db47180bed0a"

    MAX_THROTTLE_PERIOD = 60


class Hosted(Config):
    HOST = "hosted"
    TENANT = f"{os.environ.get('TENANT')}." if os.environ.get("TENANT") is not None else ""
    SUBDOMAIN = (
        "dev."
        if os.environ.get("ENVIRONMENT") == "development"
        else f"{os.environ.get('ENVIRONMENT')}."
        if os.environ.get("ENVIRONMENT") != "production"
        else ""
    )
    ADMIN_BASE_URL = f"http://admin.{TENANT}ecs.local:6012"
    ADMIN_EXTERNAL_URL = f"https://{TENANT}admin.{SUBDOMAIN}emergency-alerts.service.gov.uk"
    REDIS_URL = f"redis://api.{TENANT}ecs.local:6379/0"
    API_HOST_NAME = f"http://api.{TENANT}ecs.local:6011"
    TEMPLATE_PREVIEW_API_HOST = f"http://api.{TENANT}ecs.local:6013"
    if os.getenv("MASTER_USERNAME"):
        print("Using master credentials for db connection")
        filtered_password = os.environ.get("MASTER_PASSWORD").replace("%", "%%")
        SQLALCHEMY_DATABASE_URI = "postgresql://{user}:{password}@{host}:{port}/{database}".format(
            user=os.environ.get("MASTER_USERNAME"),
            password=filtered_password,
            host=os.environ.get("RDS_HOST"),
            port=os.environ.get("RDS_PORT"),
            database=os.environ.get("DATABASE"),
        )
    else:
        SQLALCHEMY_DATABASE_URI = (
            "postgresql://{user}@{host}:{port}/{database}?sslmode=verify-full&sslrootcert={cert}".format(
                user=os.environ.get("RDS_USER"),
                host=os.environ.get("RDS_HOST"),
                port=os.environ.get("RDS_PORT"),
                database=os.environ.get("DATABASE"),
                cert="/etc/ssl/certs/global-bundle.pem",
            )
        )
    CBC_PROXY_ENABLED = True
    DEBUG = False


class Test(Config):
    NOTIFY_EMAIL_DOMAIN = "test.notify.com"
    FROM_NUMBER = "testing"
    HOST = "test"
    TESTING = True

    SQLALCHEMY_DATABASE_URI = "postgresql://{user}:{password}@{host}:{port}/{database}".format(
        user=os.environ.get("TEST_RDS_USER", "postgres"),
        password=os.environ.get("TEST_RDS_PASSWORD", "root"),
        host=os.environ.get("TEST_RDS_HOST", "pg"),
        port=os.environ.get("TEST_RDS_PORT", 5432),
        database=os.environ.get("TEST_DATABASE", "test_emergency_alerts"),
    )
    SQLALCHEMY_RECORD_QUERIES = False

    CELERY = {**Config.CELERY, "broker_url": "you-forgot-to-mock-celery-in-your-tests://"}

    API_RATE_LIMIT_ENABLED = True
    API_HOST_NAME = "http://localhost:6011"

    TENANT = f"{os.environ.get('TENANT')}." if os.environ.get("TENANT") is not None else ""
    SUBDOMAIN = (
        "dev."
        if os.environ.get("ENVIRONMENT") == "development"
        else f"{os.environ.get('ENVIRONMENT')}."
        if os.environ.get("ENVIRONMENT") != "production"
        else ""
    )
    ADMIN_EXTERNAL_URL = f"https://{TENANT}admin.{SUBDOMAIN}emergency-alerts.service.gov.uk"
    REPORTS_SLACK_WEBHOOK_URL = "https://hooks.slack.com/somewhere"
    CBC_PROXY_ENABLED = True


configs = {
    "local": Config,
    "hosted": Hosted,
    "test": Test,
}
