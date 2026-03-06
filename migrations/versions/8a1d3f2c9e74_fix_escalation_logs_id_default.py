"""fix escalation_logs id default sequence

Revision ID: 8a1d3f2c9e74
Revises: 6f2b8c1d4a11
Create Date: 2026-03-05 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8a1d3f2c9e74"
down_revision: Union[str, Sequence[str], None] = "6f2b8c1d4a11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'S'
                  AND c.relname = 'escalation_logs_id_seq'
            ) THEN
                CREATE SEQUENCE escalation_logs_id_seq;
            END IF;

            ALTER TABLE escalation_logs
            ALTER COLUMN id SET DEFAULT nextval('escalation_logs_id_seq');

            ALTER SEQUENCE escalation_logs_id_seq
            OWNED BY escalation_logs.id;

            PERFORM setval(
                'escalation_logs_id_seq',
                COALESCE((SELECT MAX(id) FROM escalation_logs), 0) + 1,
                false
            );
        END
        $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        ALTER TABLE escalation_logs
        ALTER COLUMN id DROP DEFAULT;
        """
    )
