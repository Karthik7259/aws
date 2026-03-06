"""add admin otp verification fields

Revision ID: 9c7b2d1e4f6a
Revises: 8a1d3f2c9e74
Create Date: 2026-03-06 10:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c7b2d1e4f6a"
down_revision: Union[str, Sequence[str], None] = "8a1d3f2c9e74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("department_admins", sa.Column("phone_number", sa.String(length=20), nullable=True))
    op.add_column(
        "department_admins",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "department_admins",
        sa.Column("phone_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("department_admins", sa.Column("email_otp_hash", sa.String(length=255), nullable=True))
    op.add_column("department_admins", sa.Column("phone_otp_hash", sa.String(length=255), nullable=True))
    op.add_column("department_admins", sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True))

    # Keep existing admins able to login after rollout.
    op.execute(
        """
        UPDATE department_admins
        SET email_verified = true,
            phone_verified = true
        WHERE is_active = true
        """
    )

    op.alter_column("department_admins", "email_verified", server_default=None)
    op.alter_column("department_admins", "phone_verified", server_default=None)


def downgrade() -> None:
    op.drop_column("department_admins", "otp_expires_at")
    op.drop_column("department_admins", "phone_otp_hash")
    op.drop_column("department_admins", "email_otp_hash")
    op.drop_column("department_admins", "phone_verified")
    op.drop_column("department_admins", "email_verified")
    op.drop_column("department_admins", "phone_number")
