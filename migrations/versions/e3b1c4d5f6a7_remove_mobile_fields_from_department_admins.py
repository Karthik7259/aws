"""remove mobile fields from department admins

Revision ID: e3b1c4d5f6a7
Revises: 9c7b2d1e4f6a
Create Date: 2026-03-06 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e3b1c4d5f6a7"
down_revision: Union[str, Sequence[str], None] = "9c7b2d1e4f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("department_admins", "phone_otp_hash")
    op.drop_column("department_admins", "phone_verified")
    op.drop_column("department_admins", "phone_number")


def downgrade() -> None:
    op.add_column("department_admins", sa.Column("phone_number", sa.String(length=20), nullable=True))
    op.add_column(
        "department_admins",
        sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("department_admins", sa.Column("phone_otp_hash", sa.String(length=255), nullable=True))
    op.alter_column("department_admins", "phone_verified", server_default=None)
