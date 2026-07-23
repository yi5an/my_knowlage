"""hide historical scheduled and live broadcast failures

Revision ID: 202607230001
Revises: 202607170003
Create Date: 2026-07-23
"""

from alembic import op

revision = "202607230001"
down_revision = "202607170003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE video
        SET fetch_status = 'ignored_live',
            error_message = 'ignored live broadcast'
        WHERE fetch_status = 'failed'
          AND (
            lower(error_message) LIKE '%this live event will begin%'
            OR lower(error_message) LIKE '%this live event is scheduled%'
            OR lower(error_message) LIKE '%this live event is currently live%'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE video
        SET fetch_status = 'failed'
        WHERE fetch_status = 'ignored_live'
          AND error_message = 'ignored live broadcast'
        """
    )
