"""

Revision ID: 0403_add_common_passwords_table
Revises: 0402_drop_deprecated_tables
Create Date: 2024-10-31 11:33:35

"""

import os

import boto3
import botocore
import sqlalchemy as sa
from alembic import op

from app.utils import is_local_host

revision = "0403_add_common_passwords_table"
down_revision = "0402_drop_deprecated_tables"


s3 = boto3.client("s3")
passwords_file = os.getenv("COMMON_PASSWORDS_FILEPATH", "")
common_passwords_bucket_name = os.getenv("COMMON_PASSWORDS_BUCKET_NAME", "")


def upgrade():
    common_passwords_table = op.create_table(
        "common_passwords",
        sa.Column("password", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("password"),
    )

    op.create_index(
        op.f("ix_common_password"),
        "common_passwords",
        ["password"],
        unique=True,
    )
    if is_local_host() and os.path.exists(passwords_file):
        with open(passwords_file, "r") as file:
            passwords = file.readlines()
        if passwords:
            bulk_insert_passwords(passwords, common_passwords_table)
    elif (common_passwords_bucket_name != "") and (
        check_file_exists(common_passwords_bucket_name, "passwords.txt")
    ):
        if passwords := get_file_contents_from_s3(common_passwords_bucket_name, "passwords.txt"):
            bulk_insert_passwords(passwords, common_passwords_table)
        else:
            print("Passwords file was empty")
    else:
        print("No common passwords file found")


def downgrade():
    op.drop_table("common_passwords")


def get_file_contents_from_s3(bucket, file):
    response = s3.get_object(Bucket=bucket, Key=file)
    return response["Body"].read().decode("utf-8").splitlines()


def bulk_insert_passwords(passwords, table):
    data = [password.strip() for password in passwords if password != ""]
    op.bulk_insert(table, [{"password": row} for row in data])


def check_file_exists(bucket, file):
    try:
        s3.head_object(Bucket=bucket, Key=file)
        return True
    except botocore.exceptions.ClientError as err:
        if err.response["Error"]["Code"] == "403":
            print("File not found")
        else:
            print("Error:", err)
        return False
