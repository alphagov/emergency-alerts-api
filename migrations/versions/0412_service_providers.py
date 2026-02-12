"""

Revision ID: 0412_service_providers
Revises: 0411_broadcast_message_history
Create Date: 2025-03-24 11:16:00

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0412_service_providers"
down_revision = "0411_broadcast_message_history"


def upgrade():
    op.create_table(
        "service_broadcast_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["provider"],
            ["broadcast_provider_types.name"],
        ),
    )
    op.execute("""
        INSERT INTO broadcast_provider_types
        SELECT 'deprecated'
        """)

    # Migrate the 'all' specifier in the service_broadcast_settings table
    # to individual providers in the service_broadcast_providers table
    op.execute("""
        DO $$
            DECLARE
                provider_itr TEXT;
                providers TEXT[] := ARRAY['ee', 'o2', 'three', 'vodafone'];
            BEGIN
                FOREACH provider_itr IN ARRAY providers LOOP
                    INSERT INTO service_broadcast_providers
                        (id, service_id, provider, created_at)
                    SELECT gen_random_uuid(), service_id, provider_itr, NOW()
                    FROM service_broadcast_settings
                    WHERE service_id IN (
                        SELECT id
                        FROM services
                        WHERE active = true
                    ) AND provider = 'all';
            END LOOP;
        END $$;
        """)

    # Migrate the original single-provider services
    op.execute("""
        INSERT INTO service_broadcast_providers
            (id, service_id, provider, created_at)
        SELECT gen_random_uuid(), service_id, provider, NOW()
        FROM service_broadcast_settings
        WHERE service_id IN (
                SELECT id
            FROM services
            WHERE active = true
            )
            AND provider IN ('ee', 'o2', 'three', 'vodafone')
        """)


def downgrade():
    op.drop_table("service_broadcast_providers")
    op.execute("""
        DELETE FROM broadcast_provider_types
        WHERE name = 'deprecated'
        """)
