"""seed departments

Revision ID: b00043d92dab
Revises: c0b13b0daef4
Create Date: 2026-03-04 19:17:14.246959

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b00043d92dab'
down_revision: Union[str, Sequence[str], None] = 'c0b13b0daef4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.bulk_insert(
        sa.table(
            "departments",
            sa.column("name", sa.String),
            sa.column("is_active", sa.Boolean),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {"name": "Public Works Department (PWD)", "is_active": True, "created_at": datetime.now(timezone.utc)},
            {"name": "Health & Family Welfare Department", "is_active": True, "created_at": datetime.now(timezone.utc)},
            {"name": "Education Department", "is_active": True, "created_at": datetime.now(timezone.utc)},
            {"name": "Municipal Corporation / Urban Local Body", "is_active": True, "created_at": datetime.now(timezone.utc)},
            {"name": "Police Department (Home Department)", "is_active": True, "created_at": datetime.now(timezone.utc)},
            {"name": "Electricity & Power Department", "is_active": True, "created_at": datetime.now(timezone.utc)},
            {"name": "Social Welfare Department", "is_active": True, "created_at": datetime.now(timezone.utc)},
        ]
    )


def downgrade() -> None:
    op.execute("DELETE FROM departments")