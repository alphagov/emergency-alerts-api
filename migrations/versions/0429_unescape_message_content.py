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


def upgrade():
    # unescape the broadcast message `content` data
    conn = op.get_bind()

    fetch_content_sql = sa.select(BroadcastMessage.id, BroadcastMessage.content)
    results = conn.execute(fetch_content_sql)

    for message_id, original_content in results:
        if original_content is None:
            continue

        unescaped_content = unescape(original_content)

        # If content has been changed, update the stored value
        if unescaped_content != original_content:
            conn.execute(
                sa.update(BroadcastMessage).where(BroadcastMessage.id == message_id).values(content=unescaped_content)
            )


def downgrade():
    # escape the broadcast message `content` data
    conn = op.get_bind()

    fetch_content_sql = sa.select(BroadcastMessage.id, BroadcastMessage.content)
    results = conn.execute(fetch_content_sql)

    for message_id, original_content in results:
        if original_content is None:
            continue

        escaped_content = escape(original_content)

        # If content has been changed, update the stored value
        if escaped_content != original_content:
            conn.execute(
                sa.update(BroadcastMessage).where(BroadcastMessage.id == message_id).values(content=escaped_content)
            )
