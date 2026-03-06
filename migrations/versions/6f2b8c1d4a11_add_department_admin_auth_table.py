"""add department admin auth table

Revision ID: 6f2b8c1d4a11
Revises: 4d9b1f4b7e7c
Create Date: 2026-03-04 22:00:00.000000

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f2b8c1d4a11"
down_revision: Union[str, Sequence[str], None] = "4d9b1f4b7e7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEPARTMENTS = [
    "Education",
    "Electricity and Power",
    "Health and Family Welfare",
    "Municipal Corporation",
    "Police Department",
    "Public Works Department",
    "Social Welfare",
]


def upgrade() -> None:
    op.create_table(
        "department_admins",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("department_id", sa.Integer(), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_department_admins_email"), "department_admins", ["email"], unique=True)

    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    for name in DEPARTMENTS:
        exists = conn.execute(
            sa.text("SELECT id FROM departments WHERE lower(name) = lower(:name) LIMIT 1"),
            {"name": name},
        ).fetchone()
        if exists is None:
            conn.execute(
                sa.text(
                    "INSERT INTO departments (name, is_active, created_at) VALUES (:name, :is_active, :created_at)"
                ),
                {"name": name, "is_active": True, "created_at": now},
            )


def downgrade() -> None:
    op.drop_index(op.f("ix_department_admins_email"), table_name="department_admins")
    op.drop_table("department_admins")
