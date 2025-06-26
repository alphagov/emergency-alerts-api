import os
from contextlib import contextmanager

import pytest
import sqlalchemy
from alembic.command import upgrade
from alembic.config import Config

from app import create_app, db
from app.notify_api_flask_app import NotifyApiFlaskApp


@pytest.fixture(scope="session")
def notify_api():
    app = NotifyApiFlaskApp("test")
    create_app(app)

    # deattach server-error error handlers - error_handler_spec looks like:
    #   {'blueprint_name': {
    #       status_code: [error_handlers],
    #       None: { ExceptionClass: error_handler }
    # }}
    for error_handlers in app.error_handler_spec.values():
        error_handlers.pop(500, None)
        if None in error_handlers:
            error_handlers[None] = {
                exc_class: error_handler
                for exc_class, error_handler in error_handlers[None].items()
                if exc_class != Exception
            }
            if error_handlers[None] == []:
                error_handlers.pop(None)

    ctx = app.app_context()
    ctx.push()

    yield app

    ctx.pop()


@pytest.fixture(scope="function")
def client(notify_api):
    with notify_api.test_request_context(), notify_api.test_client() as client:
        yield client


def create_test_db(database_uri):
    # get the
    db_uri_parts = database_uri.split("/")
    postgres_db_uri = "/".join(db_uri_parts[:-1] + ["postgres"])

    postgres_db = sqlalchemy.create_engine(
        postgres_db_uri, echo=False, isolation_level="AUTOCOMMIT", client_encoding="utf8"
    )
    try:
        result = postgres_db.execute(sqlalchemy.sql.text("CREATE DATABASE {}".format(db_uri_parts[-1])))
        result.close()
    except sqlalchemy.exc.ProgrammingError:
        # database "test_emergency_alerts_master" already exists
        pass
    finally:
        postgres_db.dispose()


@pytest.fixture(scope="session")
def _notify_db(notify_api, worker_id):
    """
    Manages the connection to the database. Generally this shouldn't be used, instead you should use the
    `notify_db_session` fixture which also cleans up any data you've got left over after your test run.
    """
    from flask import current_app

    assert "test_emergency_alerts" in db.engine.url.database, "dont run tests against main db"

    # create a database for this worker thread -
    current_app.config["SQLALCHEMY_DATABASE_URI"] += "_{}".format(worker_id)

    # get rid of the old SQLAlchemy instance because we can’t have multiple on the same app
    notify_api.extensions.pop("sqlalchemy")

    # reinitalise the db so it picks up on the new test database name
    db.init_app(notify_api)
    create_test_db(current_app.config["SQLALCHEMY_DATABASE_URI"])

    BASE_DIR = os.path.dirname(os.path.dirname(__file__))
    ALEMBIC_CONFIG = os.path.join(BASE_DIR, "migrations")
    config = Config(ALEMBIC_CONFIG + "/alembic.ini")
    config.set_main_option("script_location", ALEMBIC_CONFIG)

    with notify_api.app_context():
        upgrade(config, "head")

        db.session.execute(
            f"SET statement_timeout = {current_app.config['DATABASE_STATEMENT_TIMEOUT_MS']}",
        )
        db.session.execute(
            f"SET application_name = {current_app.config['EAS_APP_NAME']}",
        )

        yield db

        db.session.remove()
        db.engine.dispose()


@pytest.fixture(scope="function")
def notify_db_session(_notify_db):
    """
    This fixture clears down all non static data after your test run. It yields the sqlalchemy session variable
    so you can manually add, commit, etc if needed.

    `notify_db_session.commit()`
    """
    yield _notify_db.session

    _clean_database(_notify_db)


def _clean_database(_db):
    _db.session.remove()
    for tbl in reversed(_db.metadata.sorted_tables):
        if tbl.name not in [
            "key_types",
            "organisation_types",
            "service_permission_types",
            "auth_type",
            "broadcast_status_type",
            "invite_status_type",
            "service_callback_type",
            "broadcast_channel_types",
            "broadcast_provider_types",
        ]:
            _db.engine.execute(tbl.delete())
    _db.session.commit()


@pytest.fixture
def os_environ():
    """
    clear os.environ, and restore it after the test runs
    """
    # for use whenever you expect code to edit environment variables
    old_env = os.environ.copy()
    os.environ.clear()

    yield

    # clear afterwards in case anything extra was added to the environment during the test
    os.environ.clear()
    for k, v in old_env.items():
        os.environ[k] = v


def pytest_generate_tests(metafunc):
    # Copied from https://gist.github.com/pfctdayelise/5719730
    idparametrize = metafunc.definition.get_closest_marker("idparametrize")
    if idparametrize:
        argnames, testdata = idparametrize.args
        ids, argvalues = zip(*sorted(testdata.items()))
        metafunc.parametrize(argnames, argvalues, ids=ids)


@contextmanager
def set_config(app, name, value):
    old_val = app.config.get(name)
    app.config[name] = value
    try:
        yield
    finally:
        app.config[name] = old_val


@contextmanager
def set_config_values(app, dict):
    old_values = {}

    for key in dict:
        old_values[key] = app.config.get(key)
        app.config[key] = dict[key]

    try:
        yield
    finally:
        for key in dict:
            app.config[key] = old_values[key]


class Matcher:
    def __init__(self, description, key):
        self.description = description
        self.key = key

    def __eq__(self, other):
        return self.key(other)

    def __repr__(self):
        return "<Matcher: {}>".format(self.description)
