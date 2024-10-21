"""

Revision ID: 0401_drop_job_tables
Revises: 0400_add_password_history_table
Create Date: 2024-05-10 10:00:00

"""

from alembic import op

revision = "0401_drop_job_tables"
down_revision = "0400_add_password_history_table"


def upgrade():
    op.drop_table("notifications")
    op.drop_table("notification_history")
    op.drop_table("notification_status_types")
    op.execute("DROP VIEW notifications_all_time_view")
    op.drop_table("jobs")
    op.drop_table("job_status")
    op.drop_table("ft_billing")
    op.drop_table("ft_notification_status")
    op.drop_table("ft_processing_time")
    pass


def downgrade():
    pass
