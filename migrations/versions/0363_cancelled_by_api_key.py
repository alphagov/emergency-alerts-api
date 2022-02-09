"""

Revision ID: 0363_cancelled_by_api_key
Revises: 0362_broadcast_msg_event
Create Date: 2022-01-25 18:05:27.750234

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0363_cancelled_by_api_key'
down_revision = '0362_broadcast_msg_event'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('broadcast_message', sa.Column('created_by_api_key_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        'broadcast_message', sa.Column('cancelled_by_api_key_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.drop_constraint('broadcast_message_api_key_id_fkey', 'broadcast_message', type_='foreignkey')
    op.create_foreign_key(
        'broadcast_message_created_by_api_key_id_fkey',
        'broadcast_message',
        'api_keys',
        ['created_by_api_key_id'],
        ['id']
    )
    op.create_foreign_key(
        'broadcast_message_cancelled_by_api_key_id_fkey',
        'broadcast_message',
        'api_keys',
        ['cancelled_by_api_key_id'],
        ['id']
    )
    op.create_check_constraint(
        "ck_broadcast_message_created_by_not_null",
        "broadcast_message",
        "created_by_id is not null or created_by_api_key_id is not null"
    )
    op.get_bind()
    op.execute("UPDATE broadcast_message SET created_by_api_key_id=api_key_id")  # move data over
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(
        "ck_broadcast_message_created_by_not_null",
        "broadcast_message"
    )
    op.drop_constraint('broadcast_message_created_by_api_key_id_fkey', 'broadcast_message', type_='foreignkey')
    op.drop_constraint('broadcast_message_cancelled_by_api_key_id_fkey', 'broadcast_message', type_='foreignkey')
    op.create_foreign_key('broadcast_message_api_key_id_fkey', 'broadcast_message', 'api_keys', ['api_key_id'], ['id'])
    op.get_bind()
    op.execute("UPDATE broadcast_message SET api_key_id=created_by_api_key_id")  # move data over
    op.drop_column('broadcast_message', 'cancelled_by_api_key_id')
    op.drop_column('broadcast_message', 'created_by_api_key_id')
    # ### end Alembic commands ###
