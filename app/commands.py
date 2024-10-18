import csv
import functools
import itertools
import os
import uuid
from datetime import datetime, timedelta

import click
import flask
from click_datetime import Datetime as click_dt
from emergency_alerts_utils.statsd_decorators import statsd
from flask import current_app, json
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from app import db
from app.dao.broadcast_message_dao import dao_purge_old_broadcast_messages
from app.dao.invited_user_dao import delete_invitations_sent_by_user
from app.dao.organisation_dao import (
    dao_add_service_to_organisation,
    dao_get_organisation_by_email_address,
    dao_get_organisation_by_id,
)
from app.dao.permissions_dao import permission_dao
from app.dao.services_dao import (
    dao_fetch_all_services_by_user,
    dao_fetch_all_services_created_by_user,
    dao_fetch_service_by_id,
    dao_update_service,
    delete_service_and_all_associated_db_objects,
)
from app.dao.template_folder_dao import dao_purge_template_folders_for_service
from app.dao.templates_dao import dao_purge_templates_for_service
from app.dao.users_dao import (
    delete_model_user,
    delete_user_verify_codes,
    get_user_by_email,
)
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


@notify_command()
def backfill_notification_statuses():
    """
    DEPRECATED. Populates notification_status.

    This will be used to populate the new `Notification._status_fkey` with the old
    `Notification._status_enum`
    """
    LIMIT = 250000
    subq = "SELECT id FROM notification_history WHERE notification_status is NULL LIMIT {}".format(LIMIT)
    update = "UPDATE notification_history SET notification_status = status WHERE id in ({})".format(subq)
    result = db.session.execute(subq).fetchall()

    while len(result) > 0:
        db.session.execute(update)
        print("commit {} updates at {}".format(LIMIT, datetime.utcnow()))
        db.session.commit()
        result = db.session.execute(subq).fetchall()


@notify_command()
def update_notification_international_flag():
    """
    DEPRECATED. Set notifications.international=false.
    """
    # 250,000 rows takes 30 seconds to update.
    subq = "select id from notifications where international is null limit 250000"
    update = "update notifications set international = False where id in ({})".format(subq)
    result = db.session.execute(subq).fetchall()

    while len(result) > 0:
        db.session.execute(update)
        print("commit 250000 updates at {}".format(datetime.utcnow()))
        db.session.commit()
        result = db.session.execute(subq).fetchall()

    # Now update notification_history
    subq_history = "select id from notification_history where international is null limit 250000"
    update_history = "update notification_history set international = False where id in ({})".format(subq_history)
    result_history = db.session.execute(subq_history).fetchall()
    while len(result_history) > 0:
        db.session.execute(update_history)
        print("commit 250000 updates at {}".format(datetime.utcnow()))
        db.session.commit()
        result_history = db.session.execute(subq_history).fetchall()


@notify_command()
def fix_notification_statuses_not_in_sync():
    """
    DEPRECATED.
    This will be used to correct an issue where Notification._status_enum and NotificationHistory._status_fkey
    became out of sync. See 979e90a.

    Notification._status_enum is the source of truth so NotificationHistory._status_fkey will be updated with
    these values.
    """
    MAX = 10000

    subq = "SELECT id FROM notifications WHERE cast (status as text) != notification_status LIMIT {}".format(MAX)
    update = "UPDATE notifications SET notification_status = status WHERE id in ({})".format(subq)
    result = db.session.execute(subq).fetchall()

    while len(result) > 0:
        db.session.execute(update)
        print("Committed {} updates at {}".format(len(result), datetime.utcnow()))
        db.session.commit()
        result = db.session.execute(subq).fetchall()

    subq_hist = (
        "SELECT id FROM notification_history WHERE cast (status as text) != notification_status LIMIT {}".format(MAX)
    )
    update = "UPDATE notification_history SET notification_status = status WHERE id in ({})".format(subq_hist)
    result = db.session.execute(subq_hist).fetchall()

    while len(result) > 0:
        db.session.execute(update)
        print("Committed {} updates at {}".format(len(result), datetime.utcnow()))
        db.session.commit()
        result = db.session.execute(subq_hist).fetchall()


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
    #  send messages ==> send_texts | send_emails | send_letters
    #  Access API keys manage_api_keys
    #  platform_admin
    #  view_activity
    # "send_texts,send_emails,send_letters,view_activity"
    from app.service_invite.rest import create_invited_user

    file = open(file_name)
    for email_address in file:
        data = {
            "service": service_id,
            "email_address": email_address.strip(),
            "from_user": user_id,
            "permissions": permissions,
            "auth_type": auth_type,
            # "invite_link_host": current_app.config["ADMIN_BASE_URL"],
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


@notify_command(name="populate-notification-postage")
@click.option(
    "-s", "--start_date", default=datetime(2017, 2, 1), help="start date inclusive", type=click_dt(format="%Y-%m-%d")
)
@statsd(namespace="tasks")
def populate_notification_postage(start_date):
    current_app.logger.info("populating historical notification postage")

    total_updated = 0

    while start_date < datetime.utcnow():
        # process in ten day chunks
        end_date = start_date + timedelta(days=10)

        sql = """
            UPDATE {}
            SET postage = 'second'
            WHERE notification_type = 'letter' AND
            postage IS NULL AND
            created_at BETWEEN :start AND :end
            """

        execution_start = datetime.utcnow()

        if end_date > datetime.utcnow() - timedelta(days=8):
            print("Updating notifications table as well")
            db.session.execute(sql.format("notifications"), {"start": start_date, "end": end_date})

        result = db.session.execute(sql.format("notification_history"), {"start": start_date, "end": end_date})
        db.session.commit()

        current_app.logger.info(
            "notification postage took {}ms. Migrated {} rows for {} to {}".format(
                datetime.utcnow() - execution_start, result.rowcount, start_date, end_date
            )
        )

        start_date += timedelta(days=10)

        total_updated += result.rowcount

    current_app.logger.info("Total inserted/updated records = {}".format(total_updated))


@notify_command(name="update-emails-to-remove-gsi")
@click.option("-s", "--service_id", required=True, help="service id. Update all user.email_address to remove .gsi")
@statsd(namespace="tasks")
def update_emails_to_remove_gsi(service_id):
    users_to_update = """SELECT u.id user_id, u.name, email_address, s.id, s.name
                           FROM users u
                           JOIN user_to_service us on (u.id = us.user_id)
                           JOIN services s on (s.id = us.service_id)
                          WHERE s.id = :service_id
                            AND u.email_address ilike ('%.gsi.gov.uk%')
    """
    results = db.session.execute(users_to_update, {"service_id": service_id})
    print("Updating {} users.".format(results.rowcount))

    for user in results:
        print("User with id {} updated".format(user.user_id))

        update_stmt = """
        UPDATE users
           SET email_address = replace(replace(email_address, '.gsi.gov.uk', '.gov.uk'), '.GSI.GOV.UK', '.GOV.UK'),
               updated_at = now()
         WHERE id = :user_id
        """
        db.session.execute(update_stmt, {"user_id": str(user.user_id)})
        db.session.commit()


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
                "agreement_signed": boolean_or_none(columns[3]),
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


@notify_command(name="populate-organisation-agreement-details-from-file")
@click.option(
    "-f",
    "--file_name",
    required=True,
    help="CSV file containing id, agreement_signed_version, " "agreement_signed_on_behalf_of_name, agreement_signed_at",
)
def populate_organisation_agreement_details_from_file(file_name):
    """
    The input file should be a comma separated CSV file with a header row and 4 columns
    id: the organisation ID
    agreement_signed_version
    agreement_signed_on_behalf_of_name
    agreement_signed_at: The date the agreement was signed in the format of 'dd/mm/yyyy'
    """
    with open(file_name) as f:
        csv_reader = csv.reader(f)

        # ignore the header row
        next(csv_reader)

        for row in csv_reader:
            org = dao_get_organisation_by_id(row[0])

            current_app.logger.info(f"Updating {org.name}")

            assert org.agreement_signed

            org.agreement_signed_version = float(row[1])
            org.agreement_signed_on_behalf_of_name = row[2].strip()
            org.agreement_signed_at = datetime.strptime(row[3], "%d/%m/%Y")

            db.session.add(org)
            db.session.commit()


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


@notify_command(name="populate-service-volume-intentions")
@click.option("-f", "--file_name", required=True, help="Pipe delimited file containing service_id, SMS, email, letters")
def populate_service_volume_intentions(file_name):
    # [0] service_id
    # [1] SMS:: volume intentions for service
    # [2] Email:: volume intentions for service
    # [3] Letters:: volume intentions for service

    with open(file_name, "r") as f:
        for line in itertools.islice(f, 1, None):
            columns = line.split(",")
            print(columns)
            service = dao_fetch_service_by_id(columns[0])
            service.volume_sms = columns[1]
            service.volume_email = columns[2]
            service.volume_letter = columns[3]
            dao_update_service(service)
    print("populate-service-volume-intentions complete")


@notify_command(name="populate-go-live")
@click.option("-f", "--file_name", required=True, help="CSV file containing live service data")
def populate_go_live(file_name):
    # 0 - count, 1- Link, 2- Service ID, 3- DEPT, 4- Service Name, 5- Main contact,
    # 6- Contact detail, 7-MOU, 8- LIVE date, 9- SMS, 10 - Email, 11 - Letters, 12 -CRM, 13 - Blue badge
    import csv

    print("Populate go live user and date")
    with open(file_name, "r") as f:
        rows = csv.reader(
            f,
            quoting=csv.QUOTE_MINIMAL,
            skipinitialspace=True,
        )
        print(next(rows))  # ignore header row
        for index, row in enumerate(rows):
            print(index, row)
            service_id = row[2]
            go_live_email = row[6]
            go_live_date = datetime.strptime(row[8], "%d/%m/%Y") + timedelta(hours=12)
            print(service_id, go_live_email, go_live_date)
            try:
                if go_live_email:
                    go_live_user = get_user_by_email(go_live_email)
                else:
                    go_live_user = None
            except NoResultFound:
                print("No user found for email address: ", go_live_email)
                continue
            try:
                service = dao_fetch_service_by_id(service_id)
            except NoResultFound:
                print("No service found for: ", service_id)
                continue
            service.go_live_user = go_live_user
            service.go_live_at = go_live_date
            dao_update_service(service)


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
