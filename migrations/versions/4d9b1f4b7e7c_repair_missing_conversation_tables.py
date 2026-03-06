"""repair missing conversation tables

Revision ID: 4d9b1f4b7e7c
Revises: 33d205ff6f0e
Create Date: 2026-03-04 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d9b1f4b7e7c"
down_revision: Union[str, Sequence[str], None] = "33d205ff6f0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("citizen_feedback"):
        op.create_table(
            "citizen_feedback",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("ticket_id", sa.String(length=15), nullable=False),
            sa.Column("rating", sa.Integer(), nullable=False),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    citizen_indexes = {idx["name"] for idx in inspector.get_indexes("citizen_feedback")}
    citizen_ticket_idx = op.f("ix_citizen_feedback_ticket_id")
    if citizen_ticket_idx not in citizen_indexes:
        op.create_index(citizen_ticket_idx, "citizen_feedback", ["ticket_id"], unique=False)

    if not inspector.has_table("conversation_sessions"):
        op.create_table(
            "conversation_sessions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("session_id", sa.String(length=36), nullable=False),
            sa.Column("messages", sa.Text(), nullable=False),
            sa.Column("extracted_data", sa.Text(), nullable=False),
            sa.Column("is_complete", sa.Boolean(), nullable=False),
            sa.Column("ticket_id", sa.String(length=15), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    conversation_indexes = {idx["name"] for idx in inspector.get_indexes("conversation_sessions")}
    session_idx = op.f("ix_conversation_sessions_session_id")
    if session_idx not in conversation_indexes:
        op.create_index(session_idx, "conversation_sessions", ["session_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_conversation_sessions_session_id")
    op.execute("DROP TABLE IF EXISTS conversation_sessions")
    op.execute("DROP INDEX IF EXISTS ix_citizen_feedback_ticket_id")
    op.execute("DROP TABLE IF EXISTS citizen_feedback")
