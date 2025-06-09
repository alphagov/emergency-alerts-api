import os
import random
import string
# import threading
import time
import uuid
from time import monotonic

import boto3
# from celery import signals
from emergency_alerts_utils import logging, request_helper
from emergency_alerts_utils.celery import NotifyCelery
from emergency_alerts_utils.clients.encryption.encryption_client import (
    Encryption,
)
from emergency_alerts_utils.clients.slack.slack_client import SlackClient
from emergency_alerts_utils.clients.zendesk.zendesk_client import ZendeskClient
from flask import (
    current_app,
    g,
    has_request_context,
    jsonify,
    make_response,
    request,
)
from flask_marshmallow import Marshmallow
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from gds_metrics import GDSMetrics
from gds_metrics.metrics import Gauge, Histogram
from sqlalchemy import event
from sqlalchemy.orm import DeclarativeBase
from werkzeug.exceptions import HTTPException as WerkzeugHTTPException
from werkzeug.local import LocalProxy

from app.clients import NotificationProviderClients
from app.clients.cbc_proxy import CBCProxyClient


class Base(DeclarativeBase):
  pass


db = SQLAlchemy(Base)
migrate = Migrate()
ma = Marshmallow()
notify_celery = NotifyCelery()
encryption = Encryption()
zendesk_client = ZendeskClient()
slack_client = SlackClient()
cbc_proxy_client = CBCProxyClient()
metrics = GDSMetrics()

notification_provider_clients = NotificationProviderClients()

api_user = LocalProxy(lambda: g.api_user)
authenticated_service = LocalProxy(lambda: g.authenticated_service)

CONCURRENT_REQUESTS = Gauge(
    "concurrent_web_request_count",
    "How many concurrent requests are currently being served",
)

# _in_celery_task = threading.local()


# def is_in_celery_task():
#     return getattr(_in_celery_task, "active", False)


def create_app(application):
    from app.config import configs

    host = os.environ["HOST"]

    application.config.from_object(configs[host])

    application.config["EAS_APP_NAME"] = application.name
    init_app(application)

    # Metrics intentionally high up to give the most accurate timing and reliability that the metric is recorded
    metrics.init_app(application)
    request_helper.init_app(application)
    db.init_app(application)

    if host != "local":
        boto_session = boto3.Session(region_name=os.environ.get("AWS_REGION", "eu-west-2"))
        rds_client = boto_session.client("rds")

        with application.app_context():

            @event.listens_for(db.engine, "do_connect")
            def receive_do_connect(dialect, conn_rec, cargs, cparams):
                token = get_authentication_token(rds_client)
                cparams["password"] = token

    migrate.init_app(application, db=db)
    ma.init_app(application)
    zendesk_client.init_app(application)
    logging.init_app(application)

    notify_celery.init_app(application)
    application.extensions["celery"] = notify_celery  # EXP-1

    encryption.init_app(application)

    cbc_proxy_client.init_app(application)

    register_blueprint(application)
    register_v2_blueprints(application)

    # avoid circular imports by importing this file later
    from app.commands import setup_commands

    setup_commands(application)

    # set up sqlalchemy events
    setup_sqlalchemy_events(application)

    return application


def register_blueprint(application):
    from app.admin_action.rest import admin_action_blueprint
    from app.authentication.auth import (
        requires_admin_auth,
        requires_govuk_alerts_auth,
        requires_no_auth,
    )
    from app.broadcast_message.rest import broadcast_message_blueprint
    from app.broadcast_message_history.rest import (
        broadcast_message_history_blueprint,
    )
    from app.common_passwords.rest import common_passwords_blueprint
    from app.events.rest import events as events_blueprint
    from app.failed_logins.rest import failed_logins_blueprint
    from app.feature_toggle.rest import feature_toggle_blueprint
    from app.govuk_alerts.rest import govuk_alerts_blueprint
    from app.organisation.invite_rest import organisation_invite_blueprint
    from app.organisation.rest import organisation_blueprint
    from app.password_history.rest import password_history_blueprint
    from app.reports.rest import reports_blueprint
    from app.service.callback_rest import service_callback_blueprint
    from app.service.rest import service_blueprint
    from app.service_invite.rest import (
        service_invite as service_invite_blueprint,
    )
    from app.status.healthcheck import status as status_blueprint
    from app.template.rest import template_blueprint
    from app.template_folder.rest import template_folder_blueprint
    from app.user.rest import user_blueprint
    from app.verify.rest import verify_code_blueprint
    from app.webauthn.rest import webauthn_blueprint

    admin_action_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(admin_action_blueprint, url_prefix="/admin-action")

    service_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(service_blueprint, url_prefix="/service")

    user_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(user_blueprint, url_prefix="/user")

    webauthn_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(webauthn_blueprint)

    template_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(template_blueprint)

    status_blueprint.before_request(requires_no_auth)
    application.register_blueprint(status_blueprint)

    verify_code_blueprint.before_request(requires_no_auth)
    application.register_blueprint(verify_code_blueprint, url_prefix="/verify-code")

    service_invite_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(service_invite_blueprint)

    organisation_invite_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(organisation_invite_blueprint)

    events_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(events_blueprint)

    service_callback_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(service_callback_blueprint)

    organisation_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(organisation_blueprint, url_prefix="/organisations")

    template_folder_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(template_folder_blueprint)

    broadcast_message_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(broadcast_message_blueprint)

    broadcast_message_history_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(broadcast_message_history_blueprint)

    feature_toggle_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(feature_toggle_blueprint)

    govuk_alerts_blueprint.before_request(requires_govuk_alerts_auth)
    application.register_blueprint(govuk_alerts_blueprint)

    failed_logins_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(failed_logins_blueprint)

    reports_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(reports_blueprint)

    password_history_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(password_history_blueprint)

    common_passwords_blueprint.before_request(requires_admin_auth)
    application.register_blueprint(common_passwords_blueprint)


def register_v2_blueprints(application):
    from app.authentication.auth import requires_auth
    from app.v2.broadcast.post_broadcast import v2_broadcast_blueprint
    from app.v2.templates.get_templates import v2_templates_blueprint

    v2_templates_blueprint.before_request(requires_auth)
    application.register_blueprint(v2_templates_blueprint)

    v2_broadcast_blueprint.before_request(requires_auth)
    application.register_blueprint(v2_broadcast_blueprint)


def get_authentication_token(rds_client):
    try:
        auth_token = rds_client.generate_db_auth_token(
            DBHostname=os.environ["RDS_HOST"],
            Port=os.environ["RDS_PORT"],
            DBUsername=os.environ["RDS_USER"],
            Region=os.environ["RDS_REGION"],
        )

        return auth_token
    except Exception as e:
        print("Could not generate auth token due to {}".format(e))


def init_app(app):
    @app.before_request
    def record_request_details():
        CONCURRENT_REQUESTS.inc()

        g.start = monotonic()
        g.endpoint = request.endpoint

    @app.after_request
    def after_request(response):
        CONCURRENT_REQUESTS.dec()

        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
        response.headers.add("Access-Control-Allow-Methods", "GET,PUT,POST,DELETE")
        response.headers.add("Strict-Transport-Security", "max-age=63072000; includeSubdomains; preload")
        response.headers.add("Referrer-Policy", "no-referrer")
        return response

    @app.errorhandler(Exception)
    def exception(error):
        app.logger.exception(error)
        # error.code is set for our exception types.
        msg = getattr(error, "message", str(error))
        code = getattr(error, "code", 500)
        return jsonify(result="error", message=msg), code

    @app.errorhandler(WerkzeugHTTPException)
    def werkzeug_exception(e):
        return make_response(jsonify(result="error", message=e.description), e.code, e.get_headers())

    @app.errorhandler(404)
    def page_not_found(e):
        msg = e.description or "Not found"
        return jsonify(result="error", message=msg), 404


def create_uuid():
    return str(uuid.uuid4())


def create_random_identifier():
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))


def setup_sqlalchemy_events(app):
    TOTAL_DB_CONNECTIONS = Gauge(
        "db_connection_total_connected",
        "How many db connections are currently held (potentially idle) by the server",
    )

    TOTAL_CHECKED_OUT_DB_CONNECTIONS = Gauge(
        "db_connection_total_checked_out",
        "How many db connections are currently checked out by web requests",
    )

    DB_CONNECTION_OPEN_DURATION_SECONDS = Histogram(
        "db_connection_open_duration_seconds",
        "How long db connections are held open for in seconds",
        ["method", "host", "path"],
    )

    # need this or db.engine isn't accessible
    with app.app_context():

        @event.listens_for(db.engine, "connect")
        def connect(dbapi_connection, connection_record):
            # connection first opened with db
            TOTAL_DB_CONNECTIONS.inc()

            cursor = dbapi_connection.cursor()

            # set these here instead of in connect_args/options to avoid the early-binding
            # issues cross-referencing config vars in the config object raises
            cursor.execute(
                "SET statement_timeout = %s",
                (current_app.config["DATABASE_STATEMENT_TIMEOUT_MS"],),
            )
            cursor.execute(
                "SET application_name = %s",
                (current_app.config["EAS_APP_NAME"],),
            )
            current_app.logger.info(f"DB CONNECT event")

        @event.listens_for(db.engine, "close")
        def close(dbapi_connection, connection_record):
            # connection closed (probably only happens with overflow connections)
            TOTAL_DB_CONNECTIONS.dec()
            current_app.logger.info(f"DB CLOSE event")

        @event.listens_for(db.engine, "checkout")
        def checkout(dbapi_connection, connection_record, connection_proxy):
            try:
                # connection given to a web worker
                TOTAL_CHECKED_OUT_DB_CONNECTIONS.inc()

                # this will overwrite any previous checkout_at timestamp
                connection_record.info["checkout_at"] = time.monotonic()

                # checkin runs after the request is already torn down, therefore we add the request_data onto the
                # connection_record as otherwise it won't have that information when checkin actually runs.
                # Note: this is not a problem for checkouts as the checkout always happens within a web request or task

                # web requests
                if has_request_context():
                    current_app.logger.info(
                        f"DB CHECKOUT inside REQUEST {request.method} "
                        f"{request.host}{request.url_rule}"
                    )
                    connection_record.info["request_data"] = {
                        "method": request.method,
                        "host": request.host,
                        "url_rule": request.url_rule.rule if request.url_rule else "No endpoint",
                    }
                # celery apps
                # elif is_in_celery_task():
                #     current_app.logger.info("DB CHECKOUT inside CELERY TASK")
                #     connection_record.info["request_data"] = {
                #         "method": "celery",
                #         "host": current_app.config["EAS_APP_NAME"],
                #         "url_rule": "task",     
                #     }
                # anything else. migrations possibly, or flask cli commands.
                else:
                    current_app.logger.info("DB CHECKOUT outside request")
                    connection_record.info["request_data"] = {
                        "method": "unknown",
                        "host": "unknown",
                        "url_rule": "unknown",
                    }
            except Exception:
                current_app.logger.exception("Exception caught for checkout event.")

        @event.listens_for(db.engine, "checkin")
        def checkin(dbapi_connection, connection_record):
            try:
                current_app.logger.info(
                    f"DB CHECKIN event from {connection_record}"
                )

                # connection returned by a web worker
                TOTAL_CHECKED_OUT_DB_CONNECTIONS.dec()

                # duration that connection was held by a single web request
                duration = time.monotonic() - connection_record.info["checkout_at"]

                DB_CONNECTION_OPEN_DURATION_SECONDS.labels(
                    connection_record.info["request_data"]["method"],
                    connection_record.info["request_data"]["host"],
                    connection_record.info["request_data"]["url_rule"],
                ).observe(duration)
            except Exception:
                current_app.logger.exception("Exception caught for checkin event.")


# @signals.task_prerun.connect
# def mark_task_active(*args, **kwargs):
#     current_app.logger.info(f"Setting celery task active flag {args} {kwargs}")
#     _in_celery_task.active = True


# @signals.task_postrun.connect
# def clear_task_context(*args, **kwargs):
#     current_app.logger.info(f"Clearing celery task active flag {args} {kwargs}")
#     _in_celery_task.active = False


# @signals.task_prerun.connect
# def store_task_context(sender=None, task_id=None, task=None, **kwargs):
#     current_app.logger.info(f"Storing celery task context for {sender.name} {task_id}")
#     _celery_task_context[task_id] = {
#         "name": sender.name,
#         "args": task.request.args,
#         "kwargs": task.request.kwargs,
#     }


# @signals.task_postrun.connect
# def clear_task_context(task_id=None, **kwargs):
#     current_app.logger.info(f"Clearing celery task context for {task_id}")
#     _celery_task_context.pop(task_id, None)
