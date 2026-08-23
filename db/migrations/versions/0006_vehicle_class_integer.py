"""store master vehicle class tags as integers

Revision ID: 0006_vehicle_class_integer
Revises: 0005_default_tag_type_rules
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_vehicle_class_integer"
down_revision = "0005_default_tag_type_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guard: only run ALTER if the column is still text/varchar.
    # Migration 0001 already creates these columns as INTEGER in fresh installs,
    # so this migration is a no-op in that case.
    op.execute(
        """
        DO $$
        BEGIN
            IF (
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'master_mt'
                  AND column_name = 'vehicle_type_tag'
            ) IN ('character varying', 'text', 'character') THEN
                ALTER TABLE master_mt
                    ALTER COLUMN vehicle_type_tag TYPE INTEGER
                    USING CASE
                        WHEN vehicle_type_tag ~ '^[0-9]+(\.0+)?$'
                            THEN vehicle_type_tag::numeric::integer
                        ELSE NULL
                    END;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF (
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'master_spbu'
                  AND column_name = 'vehicle_type_tag'
            ) IN ('character varying', 'text', 'character') THEN
                ALTER TABLE master_spbu
                    ALTER COLUMN vehicle_type_tag TYPE INTEGER
                    USING CASE
                        WHEN vehicle_type_tag ~ '^[0-9]+(\.0+)?$'
                            THEN vehicle_type_tag::numeric::integer
                        ELSE NULL
                    END;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.alter_column("master_spbu", "vehicle_type_tag", existing_type=sa.Integer(), type_=sa.String(length=80))
    op.alter_column("master_mt", "vehicle_type_tag", existing_type=sa.Integer(), type_=sa.String(length=80))
