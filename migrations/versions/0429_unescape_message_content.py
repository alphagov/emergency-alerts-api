"""

Revision ID: 0429_unescape_message_content
Revises: 0428_add_area_tables
Create Date: 2026-07-13 15:25:00

"""

from html import escape, unescape

from alembic import op
import sqlalchemy as sa

from app.models import BroadcastMessage

revision = "0429_unescape_message_content"
down_revision = "0428_add_area_tables"


def transform_broadcast_message_content(transform_func):
    conn = op.get_bind()

    fetch_content_sql = sa.select(BroadcastMessage.id, BroadcastMessage.content)
    results = conn.execute(fetch_content_sql)

    for message_id, original_content in results:
        if original_content is None:
            continue

        changed_content = transform_func(original_content)

        # If content has been changed, update the stored value
        if changed_content != original_content:
            conn.execute(
                sa.update(BroadcastMessage).where(BroadcastMessage.id == message_id).values(content=changed_content)
            )


def upgrade():
    # unescape the broadcast message `content` data
    transform_broadcast_message_content(unescape)


def downgrade():
    # escape the broadcast message `content` data
    transform_broadcast_message_content(escape)
