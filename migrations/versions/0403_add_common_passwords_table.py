"""

Revision ID: 0403_add_common_passwords_table
Revises: 0402_drop_deprecated_tables
Create Date: 2024-10-31 11:33:35

"""

import uuid

import boto3
import botocore
import sqlalchemy as sa
from alembic import op
from flask import current_app
from sqlalchemy.dialects import postgresql

from app.utils import is_local_host

revision = "0403_add_common_passwords_table"
down_revision = "0402_drop_deprecated_tables"


s3 = boto3.client("s3")
passwords_file = current_app.config["COMMON_PASSWORDS_FILEPATH"]
target_filepath = "/tmp/passwords.txt"


def upgrade():
    common_passwords_table = op.create_table(
        "common_passwords",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("password", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_common_password"),
        "common_passwords",
        ["password"],
        unique=True,
    )
    if is_local_host():
        with open(passwords_file, "r") as file:
            passwords = file.readlines()
        if passwords:
            bulk_insert_passwords(passwords, common_passwords_table)
    elif current_app.config["HOST"] == "hosted" & check_file_exists(
        current_app.config["COMMON_PASSWORDS_BUCKET_NAME"], passwords_file
    ):
        print("File exists")
        download_file_from_s3(current_app.config["COMMON_PASSWORDS_BUCKET_NAME"], passwords_file, target_filepath)
        with open(target_filepath, "r") as file:
            passwords = file.readlines()
        if passwords:
            bulk_insert_passwords(passwords, common_passwords_table)
        else:
            print("Passwords file was empty")
    else:
        print("No common passwords file found")


def downgrade():
    op.drop_table("common_passwords")


def download_file_from_s3(bucket, file, destination):
    s3.download_file(bucket, file, destination)


def bulk_insert_passwords(passwords, table):
    data = [(str(uuid.uuid4()), password.strip()) for password in passwords if password != ""]
    op.bulk_insert(table, [{"id": row[0], "password": row[1]} for row in data])


def check_file_exists(bucket, file):
    try:
        s3.head_object(Bucket=bucket, Key=file).metadata
    except botocore.exceptions.ClientError as err:
        if err.response["Error"]["Code"] == "404":
            print("File not found")
        else:
            print("Another error occured", err["Error"]["Message"])
        return False
