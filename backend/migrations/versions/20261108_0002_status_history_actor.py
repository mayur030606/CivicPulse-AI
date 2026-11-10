"""Add the authenticated actor to status-history rows.

The column is nullable so existing history rows remain unchanged. New rows
written by ``PATCH /api/v1/incidents/{incident_id}`` record the acting staff
user. If that user is later removed, the foreign key is set to ``NULL`` rather
than deleting audit history.

``app.init_db`` creates missing tables directly from the SQLAlchemy models. On
a fresh database that means ``status_history`` may already have this nullable
column before Alembic runs, so the migration checks for it first.

Revision ID: 20261108_0002
Revises: 20261108_0001
Create Date: 2026-11-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20261108_0002"
down_revision: str | None = "20261108_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMN = "changed_by_user_id"
_INDEX = "ix_status_history_changed_by_user_id"
_FK = "fk_status_history_changed_by_user_id"


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade() -> None:
    inspector = _inspector()
    if "status_history" not in inspector.get_table_names():
        # ``app.init_db`` will create the table from the current model, which
        # already includes the nullable actor column.
        return

    columns = {column["name"] for column in inspector.get_columns("status_history")}
    if _COLUMN in columns:
        return

    op.add_column(
        "status_history",
        sa.Column(_COLUMN, sa.Integer(), nullable=True),
    )
    op.create_index(
        _INDEX,
        "status_history",
        [_COLUMN],
        unique=False,
    )
    op.create_foreign_key(
        _FK,
        "status_history",
        "users",
        [_COLUMN],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    inspector = _inspector()
    if "status_history" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("status_history")}
    if _COLUMN not in columns:
        return

    foreign_keys = {
        fk["name"] for fk in inspector.get_foreign_keys("status_history")
    }
    if _FK in foreign_keys:
        op.drop_constraint(_FK, "status_history", type_="foreignkey")

    indexes = {index["name"] for index in inspector.get_indexes("status_history")}
    if _INDEX in indexes:
        op.drop_index(_INDEX, table_name="status_history")

    op.drop_column("status_history", _COLUMN)
