"""phase 17 object storage (stored_files metadata)

Revision ID: b7e2a91c40d3
Revises: 0f3c9d1a2b4e
Create Date: 2026-10-29 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b7e2a91c40d3"
down_revision: Union[str, Sequence[str], None] = "0f3c9d1a2b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create stored_files: object metadata + permissions (D24 §5)."""
    op.create_table(
        "stored_files",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("proctor_event_id", sa.UUID(), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column("mime_type", sa.String(length=96), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=True),
        sa.Column(
            "upload_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("legal_hold", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["proctor_event_id"], ["proctor_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_stored_files_storage_key"),
        sa.CheckConstraint(
            "purpose IN ('evidence_clip', 'screenshot', 'attachment')",
            name="ck_stored_files_purpose",
        ),
        sa.CheckConstraint(
            "upload_status IN ('pending', 'uploaded', 'failed', 'missing', 'deleted', 'purged')",
            name="ck_stored_files_upload_status",
        ),
    )
    op.create_index(
        "ix_stored_files_meeting_id_created_at",
        "stored_files",
        ["meeting_id", "created_at"],
    )
    op.create_index(
        "ix_stored_files_retention_expires_at",
        "stored_files",
        ["retention_expires_at"],
    )
    op.create_index(
        "uq_stored_files_proctor_event_active",
        "stored_files",
        ["proctor_event_id"],
        unique=True,
        postgresql_where=sa.text("proctor_event_id IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Drop stored_files (object-store bytes are removed by retention policy)."""
    op.drop_index(
        "uq_stored_files_proctor_event_active",
        table_name="stored_files",
        postgresql_where=sa.text("proctor_event_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.drop_index("ix_stored_files_retention_expires_at", table_name="stored_files")
    op.drop_index("ix_stored_files_meeting_id_created_at", table_name="stored_files")
    op.drop_table("stored_files")
