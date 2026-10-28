"""phase 16 exam mode proctoring

Revision ID: 0f3c9d1a2b4e
Revises: 06852267ecd1
Create Date: 2026-10-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0f3c9d1a2b4e"
down_revision: Union[str, Sequence[str], None] = "06852267ecd1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: exam kind + proctoring flag, invite roster, events."""
    op.add_column(
        "meetings",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="standard"),
    )
    op.add_column(
        "meetings",
        sa.Column("proctoring_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_check_constraint("ck_meetings_kind", "meetings", "kind IN ('standard', 'exam')")

    op.create_table(
        "meeting_invites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_id", sa.UUID(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("meeting_id", "email", name="uq_meeting_invites_meeting_email"),
    )
    op.create_index("ix_meeting_invites_meeting_id", "meeting_invites", ["meeting_id"])

    op.create_table(
        "proctor_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("meeting_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("signal", sa.String(length=24), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "signal IN "
            "('eyes_closed', 'looking_away', 'multiple_faces', 'no_face', "
            "'speaking', 'tab_hidden', 'video_blur')",
            name="ck_proctor_events_signal",
        ),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_proctor_events_meeting_id_created_at",
        "proctor_events",
        ["meeting_id", "created_at"],
    )
    op.create_index(
        "ix_proctor_events_meeting_id_user_id",
        "proctor_events",
        ["meeting_id", "user_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_proctor_events_meeting_id_user_id", table_name="proctor_events")
    op.drop_index("ix_proctor_events_meeting_id_created_at", table_name="proctor_events")
    op.drop_table("proctor_events")

    op.drop_index("ix_meeting_invites_meeting_id", table_name="meeting_invites")
    op.drop_table("meeting_invites")

    op.drop_constraint("ck_meetings_kind", "meetings", type_="check")
    op.drop_column("meetings", "proctoring_enabled")
    op.drop_column("meetings", "kind")
