import functools
import itertools
import os
import uuid

import click
import flask
from flask import current_app, json
from sqlalchemy.exc import IntegrityError

from app import db
from app.dao.broadcast_message_dao import dao_purge_old_broadcast_messages
from app.dao.invited_user_dao import delete_invitations_sent_by_user
from app.dao.organisation_dao import (
    dao_add_service_to_organisation,
    dao_get_organisation_by_email_address,
)
from app.dao.permissions_dao import permission_dao
from app.dao.services_dao import (
    dao_fetch_all_services_by_user,
    dao_fetch_all_services_created_by_user,
    dao_fetch_service_by_id,
    delete_service_and_all_associated_db_objects,
)
from app.dao.template_folder_dao import dao_purge_template_folders_for_service
from app.dao.templates_dao import dao_purge_templates_for_service
from app.dao.users_dao import delete_model_user, delete_user_verify_codes
from app.models import Domain, Organisation, Permission, Service, User
from app.utils import is_public_environment


@click.group(name="command", help="Additional commands")
def command_group():
    pass


class notify_command:
    def __init__(self, name=None):
        self.name = name

    def __call__(self, func):
        decorators = [
            functools.wraps(func),  # carry through function name, docstrings, etc.
            click.command(name=self.name),  # turn it into a click.Command
        ]

        # in the test environment the app context is already provided and having
        # another will lead to the test db connection being closed prematurely
        if os.getenv("HOST", "") != "test":
            # with_appcontext ensures the config is loaded, db connected, etc.
            decorators.insert(0, flask.cli.with_appcontext)

        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        for decorator in decorators:
            # this syntax is equivalent to e.g. "@flask.cli.with_appcontext"
            wrapper = decorator(wrapper)

        command_group.add_command(wrapper)
        return wrapper


@notify_command()
@click.option(
    "-u",
    "--user_email_prefix",
    required=True,
    help="""
    Functional test user email prefix. eg "notify-test-preview"
""",
)  # noqa
def purge_functional_test_data(user_email_prefix):
    """
    Remove non-seeded functional test data

    users, services, etc. Give an email prefix. Probably "notify-tests-preview".
    """
    users = User.query.filter(User.email_address.like("{}%".format(user_email_prefix))).all()
    for usr in users:
        # Make sure the full email includes a uuid in it
        # Just in case someone decides to use a similar email address.
        try:
            uuid.UUID(usr.email_address.split("@")[0].split("+")[1])
        except ValueError:
            print("Skipping {} as the user email doesn't contain a UUID.".format(usr.email_address))
        else:
            services = dao_fetch_all_services_by_user(usr.id)
            if services:
                print(f"Deleting user {usr.id} which is part of services")
                for service in services:
                    delete_service_and_all_associated_db_objects(service)
            else:
                services_created_by_this_user = dao_fetch_all_services_created_by_user(usr.id)
                if services_created_by_this_user:
                    # user is not part of any services but may still have been the one to create the service
                    # sometimes things get in this state if the tests fail half way through
                    # Remove the service they created (but are not a part of) so we can then remove the user
                    print(f"Deleting services created by {usr.id}")
                    for service in services_created_by_this_user:
                        delete_service_and_all_associated_db_objects(service)

                print(f"Deleting user {usr.id} which is not part of any services")
                delete_user_verify_codes(usr)
                delete_model_user(usr)


def setup_commands(application):
    application.cli.add_command(command_group)


@notify_command(name="bulk-invite-user-to-service")
@click.option(
    "-f",
    "--file_name",
    required=True,
    help="Full path of the file containing a list of email address for people to invite to a service",
)
@click.option("-s", "--service_id", required=True, help="The id of the service that the invite is for")
@click.option("-u", "--user_id", required=True, help="The id of the user that the invite is from")
@click.option(
    "-a",
    "--auth_type",
    required=False,
    help="The authentication type for the user, sms_auth or email_auth. Defaults to sms_auth if not provided",
)
@click.option("-p", "--permissions", required=True, help="Comma separated list of permissions.")
def bulk_invite_user_to_service(file_name, service_id, user_id, auth_type, permissions):
    #  permissions
    #  manage_users | manage_templates | manage_settings
    #  Access API keys manage_api_keys
    #  platform_admin
    #  view_activity
    from app.service_invite.rest import create_invited_user

    file = open(file_name)
    for email_address in file:
        data = {
            "service": service_id,
            "email_address": email_address.strip(),
            "from_user": user_id,
            "permissions": permissions,
            "auth_type": auth_type,
            "invite_link_host": current_app.config["ADMIN_EXTERNAL_URL"],
        }
        with current_app.test_request_context(
            path="/service/{}/invite/".format(service_id),
            method="POST",
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
        ):
            try:
                response = create_invited_user(service_id)
                if response[1] != 201:
                    print("*** ERROR occurred for email address: {}".format(email_address.strip()))
                print(response[0].get_data(as_text=True))
            except Exception as e:
                print("*** ERROR occurred for email address: {}. \n{}".format(email_address.strip(), e))

    file.close()


@notify_command(name="populate-organisations-from-file")
@click.option(
    "-f",
    "--file_name",
    required=True,
    help="Pipe delimited file containing organisation name, sector, crown, argeement_signed, domains",
)
def populate_organisations_from_file(file_name):
    # [0] organisation name:: name of the organisation insert if organisation is missing.
    # [1] sector:: Central | Local | NHS only
    # [2] crown:: TRUE | FALSE only
    # [3] argeement_signed:: TRUE | FALSE
    # [4] domains:: comma separated list of domains related to the organisation

    # The expectation is that the organisation, organisation_to_service
    # and user_to_organisation will be cleared before running this command.
    # Ignoring duplicates allows us to run the command again with the same file or same file with new rows.
    with open(file_name, "r") as f:

        def boolean_or_none(field):
            if field == "1":
                return True
            elif field == "0":
                return False
            elif field == "":
                return None

        for line in itertools.islice(f, 1, None):
            columns = line.split("|")
            print(columns)
            data = {
                "name": columns[0],
                "active": True,
                "crown": boolean_or_none(columns[2]),
                "organisation_type": columns[1].lower(),
            }
            org = Organisation(**data)
            try:
                db.session.add(org)
                db.session.commit()
            except IntegrityError:
                print("duplicate org", org.name)
                db.session.rollback()
            domains = columns[4].split(",")
            for d in domains:
                if len(d.strip()) > 0:
                    domain = Domain(domain=d.strip(), organisation_id=org.id)
                    try:
                        db.session.add(domain)
                        db.session.commit()
                    except IntegrityError:
                        print("duplicate domain", d.strip())
                        db.session.rollback()


@notify_command(name="associate-services-to-organisations")
def associate_services_to_organisations():
    services = Service.get_history_model().query.filter_by(version=1).all()

    for s in services:
        created_by_user = User.query.filter_by(id=s.created_by_id).first()
        organisation = dao_get_organisation_by_email_address(created_by_user.email_address)
        service = dao_fetch_service_by_id(service_id=s.id)
        if organisation:
            dao_add_service_to_organisation(service=service, organisation_id=organisation.id)

    print("finished associating services to organisations")


@click.option("-u", "--user-id", required=True)
@notify_command(name="local-dev-broadcast-permissions")
def local_dev_broadcast_permissions(user_id):
    if is_public_environment():
        current_app.logger.error("Can only be run in development")
        return

    user = User.query.filter_by(id=user_id).one()

    user_broadcast_services = Service.query.filter(
        Service.permissions.any(permission="broadcast"), Service.users.any(id=user_id)
    )

    for service in user_broadcast_services:
        permission_list = [
            Permission(service_id=service.id, user_id=user_id, permission=permission)
            for permission in [
                "reject_broadcasts",
                "cancel_broadcasts",  # required to create / approve
                "create_broadcasts",
                "approve_broadcasts",  # minimum for testing
                "manage_templates",  # unlikely but might be useful
                "view_activity",  # normally added on invite / service creation
            ]
        ]

        permission_dao.set_user_service_permission(user, service, permission_list, _commit=True, replace=True)


@notify_command(name="purge-alerts")
@click.option(
    "-o",
    "--older-than",
    required=False,
    type=int,
    help="""Alerts older than the provided value (in days) will be purged from the database""",
)
@click.option(
    "-s",
    "--service",
    required=False,
    default=None,
    help="""Service identifier""",
)
@click.option(
    "-d",
    "--dry-run",
    required=False,
    default=False,
    type=bool,
    help="""Show the IDs of the DB items selected only. The items will not be deleted""",
)
def purge_alerts_from_db(older_than, service, dry_run):
    if os.environ.get("ENVIRONMENT") not in ["local", "development", "preview"]:
        print("Alerts can only be removed from the database db in local, development and preview environments")

    print(f"Purging alerts over {older_than} days old...")
    count = dao_purge_old_broadcast_messages(service=service, days_older_than=older_than, dry_run=dry_run)
    if dry_run:
        print(
            f"Items found for purging:\n \
            BroadcastMessage: {count['msgs']}\n \
            BroadcastEvent: {count['events']}\n \
            BroadcastProviderMessage: {count['provider_msgs']}\n \
            BroadcastProviderMessageNumber: {count['msg_numbers']}"
        )
    else:
        print(f"Successfully purged {count['msgs']} broadcast messages")


@notify_command(name="purge-templates-and-folders")
@click.option(
    "-s",
    "--service",
    required=True,
    default=None,
    help="""Service identifier""",
)
def purge_templates_and_folders(service):
    if os.environ.get("ENVIRONMENT") not in ["local", "development", "preview"]:
        print(
            "Templates and folders can only be removed from the database db in local, "
            "development and preview environments"
        )

    dao_purge_templates_for_service(service_id=service)
    dao_purge_template_folders_for_service(service_id=service)

    print(f"Successfully purged templates and folders from service {service}")


@notify_command(name="purge-functional-test-services")
def purge_services_created_by_functional_test_admin():
    if os.environ.get("ENVIRONMENT") not in ["local", "development", "preview"]:
        print("Services can only be removed from the database db in local, " "development and preview environments")

    platform_admin = "c3d33860-a967-40cf-8eb4-ec1ee38a4df9"
    services = dao_fetch_all_services_created_by_user(user_id=platform_admin)
    for service in services:
        delete_service_and_all_associated_db_objects(service=service)
    delete_invitations_sent_by_user(user_id=platform_admin)

    print("Successfully purged services created by functional tests")
