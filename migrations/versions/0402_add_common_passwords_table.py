"""

Revision ID: 0402_add_common_passwords_table
Revises: 0401_drop_job_tables
Create Date: 2024-10-31 11:33:35

"""

import uuid

import boto3
import sqlalchemy as sa
from alembic import op
from flask import current_app
from sqlalchemy.dialects import postgresql

from app.aws.s3 import file_exists
from app.utils import is_local_host

revision = "0402_add_common_passwords_table"
down_revision = "0401_drop_job_tables"


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
    list_files()
    if is_local_host():
        with open(passwords_file, "r") as file:
            passwords = file.readlines()
        data = [(str(uuid.uuid4()), password.strip()) for password in passwords if password != ""]
        op.bulk_insert(common_passwords_table, [{"id": row[0], "password": row[1]} for row in data])
    elif file_exists(current_app.config["COMMON_PASSWORDS_BUCKET_NAME"], passwords_file):
        print("File exists")
        download_file_from_s3()
        with open(target_filepath, "r") as file:
            passwords = file.readlines()
        if passwords:
            data = [(str(uuid.uuid4()), password.strip()) for password in passwords if password != ""]
            op.bulk_insert(common_passwords_table, [{"id": row[0], "password": row[1]} for row in data])
        else:
            print("Passwords file was empty")
    else:
        print("No common passwords file found")


def downgrade():
    op.drop_table("common_passwords")


def download_file_from_s3():
    s3.download_file(current_app.config["COMMON_PASSWORDS_BUCKET_NAME"], passwords_file, target_filepath)


def list_files():
    response = s3.list_objects_v2(Bucket=current_app.config["COMMON_PASSWORDS_BUCKET_NAME"])
    print(response)