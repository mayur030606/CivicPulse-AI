"""Create the legacy core tables on fresh databases.

Revision ID: 20261110_0003
Revises: 20261108_0002
Create Date: 2026-11-10

This revision makes Alembic responsible for the complete application schema.
It is additive only: each table is created only when it is absent, and existing
tables are never altered, renamed, truncated, or dropped.

Existing tables are preflighted before any new table is created. If an existing
table is missing required columns, nullability, server defaults, auto-increment
behavior, primary keys, unique constraints, or foreign keys, or if a DATETIME
column has a different fractional-second precision, the migration raises an
error and leaves the table untouched for manual review. Missing required indexes
are safe to create idempotently, including after a partial MySQL DDL failure.

``users`` and ``auth_sessions`` remain owned by revision ``20261108_0001``.
This revision runs after that revision, so ``users`` is available for the
``status_history.changed_by_user_id`` foreign key.

Downgrade is intentionally non-destructive because these tables may predate
this revision and may contain live production data.
"""
import re
from collections.abc import Sequence
from dataclasses import dataclass

import sqlalchemy as sa
from alembic import op
from sqlalchemy.types import TypeEngine

# revision identifiers, used by Alembic.
revision: str = "20261110_0003"
down_revision: str | None = "20261108_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class MigrationSchemaError(RuntimeError):
    """Raised when an existing table does not match the required schema."""


@dataclass(frozen=True)
class _ColumnSpec:
    name: str
    type_: TypeEngine
    nullable: bool
    primary_key: bool = False
    autoincrement: bool = False
    server_default: str | None = None


@dataclass(frozen=True)
class _IndexSpec:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class _ForeignKeySpec:
    name: str
    columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]
    ondelete: str | None = None


@dataclass(frozen=True)
class _TableSpec:
    name: str
    columns: tuple[_ColumnSpec, ...]
    primary_key: tuple[str, ...]
    unique_constraints: tuple[tuple[str, ...], ...] = ()
    indexes: tuple[_IndexSpec, ...] = ()
    foreign_keys: tuple[_ForeignKeySpec, ...] = ()


_TABLE_SPECS: tuple[_TableSpec, ...] = (
    _TableSpec(
        "departments",
        (
            _ColumnSpec(
                "id",
                sa.Integer(),
                nullable=False,
                primary_key=True,
                autoincrement=True,
            ),
            _ColumnSpec("name", sa.String(length=100), nullable=False),
            _ColumnSpec("description", sa.Text(), nullable=True),
        ),
        primary_key=("id",),
    ),
    _TableSpec(
        "incidents",
        (
            _ColumnSpec(
                "id",
                sa.Integer(),
                nullable=False,
                primary_key=True,
                autoincrement=True,
            ),
            _ColumnSpec("tracking_id", sa.String(length=50), nullable=False),
            _ColumnSpec("category", sa.String(length=100), nullable=False),
            _ColumnSpec("description", sa.Text(), nullable=True),
            _ColumnSpec("severity", sa.String(length=30), nullable=True),
            _ColumnSpec("priority", sa.String(length=30), nullable=True),
            _ColumnSpec(
                "status",
                sa.String(length=30),
                nullable=True,
                server_default="'Submitted'",
            ),
            _ColumnSpec(
                "latitude",
                sa.Numeric(precision=10, scale=7),
                nullable=True,
            ),
            _ColumnSpec(
                "longitude",
                sa.Numeric(precision=10, scale=7),
                nullable=True,
            ),
            _ColumnSpec(
                "created_at",
                sa.DateTime(),
                nullable=True,
                server_default="CURRENT_TIMESTAMP",
            ),
        ),
        primary_key=("id",),
        unique_constraints=(("tracking_id",),),
    ),
    _TableSpec(
        "citizen_reports",
        (
            _ColumnSpec(
                "id",
                sa.Integer(),
                nullable=False,
                primary_key=True,
                autoincrement=True,
            ),
            _ColumnSpec("incident_id", sa.Integer(), nullable=True),
            _ColumnSpec("language", sa.String(length=20), nullable=True),
            _ColumnSpec("transcript", sa.Text(), nullable=True),
            _ColumnSpec(
                "created_at",
                sa.DateTime(),
                nullable=True,
                server_default="CURRENT_TIMESTAMP",
            ),
        ),
        primary_key=("id",),
        indexes=(
            _IndexSpec("ix_citizen_reports_incident_id", ("incident_id",)),
        ),
        foreign_keys=(
            _ForeignKeySpec(
                "fk_citizen_reports_incident_id",
                ("incident_id",),
                "incidents",
                ("id",),
            ),
        ),
    ),
    _TableSpec(
        "incident_images",
        (
            _ColumnSpec(
                "id",
                sa.Integer(),
                nullable=False,
                primary_key=True,
                autoincrement=True,
            ),
            _ColumnSpec("incident_id", sa.Integer(), nullable=True),
            _ColumnSpec("image_path", sa.String(length=500), nullable=True),
            _ColumnSpec("detection_result", sa.JSON(), nullable=True),
        ),
        primary_key=("id",),
        indexes=(
            _IndexSpec("ix_incident_images_incident_id", ("incident_id",)),
        ),
        foreign_keys=(
            _ForeignKeySpec(
                "fk_incident_images_incident_id",
                ("incident_id",),
                "incidents",
                ("id",),
            ),
        ),
    ),
    _TableSpec(
        "status_history",
        (
            _ColumnSpec(
                "id",
                sa.Integer(),
                nullable=False,
                primary_key=True,
                autoincrement=True,
            ),
            _ColumnSpec("incident_id", sa.Integer(), nullable=True),
            _ColumnSpec("old_status", sa.String(length=30), nullable=True),
            _ColumnSpec("new_status", sa.String(length=30), nullable=True),
            _ColumnSpec("notes", sa.Text(), nullable=True),
            _ColumnSpec("changed_by_user_id", sa.Integer(), nullable=True),
            _ColumnSpec(
                "changed_at",
                sa.DateTime(),
                nullable=True,
                server_default="CURRENT_TIMESTAMP",
            ),
        ),
        primary_key=("id",),
        indexes=(
            _IndexSpec("ix_status_history_incident_id", ("incident_id",)),
            _IndexSpec(
                "ix_status_history_changed_by_user_id",
                ("changed_by_user_id",),
            ),
        ),
        foreign_keys=(
            _ForeignKeySpec(
                "fk_status_history_incident_id",
                ("incident_id",),
                "incidents",
                ("id",),
            ),
            _ForeignKeySpec(
                "fk_status_history_changed_by_user_id",
                ("changed_by_user_id",),
                "users",
                ("id",),
                ondelete="SET NULL",
            ),
        ),
    ),
)


def _existing_tables(inspector: sa.Inspector) -> set[str]:
    """Return the tables already present, without modifying the database."""
    return set(inspector.get_table_names())


def _column_from_spec(column: _ColumnSpec) -> sa.Column:
    return sa.Column(
        column.name,
        column.type_.copy(),
        primary_key=column.primary_key,
        autoincrement=column.autoincrement,
        nullable=column.nullable,
        server_default=(
            sa.text(column.server_default)
            if column.server_default is not None
            else None
        ),
    )


def _constraints_from_spec(table: _TableSpec) -> list[sa.Constraint]:
    constraints: list[sa.Constraint] = []
    for unique_columns in table.unique_constraints:
        constraints.append(sa.UniqueConstraint(*unique_columns))
    for foreign_key in table.foreign_keys:
        constraints.append(
            sa.ForeignKeyConstraint(
                list(foreign_key.columns),
                [
                    f"{foreign_key.referred_table}.{column}"
                    for column in foreign_key.referred_columns
                ],
                name=foreign_key.name,
                ondelete=foreign_key.ondelete,
            )
        )
    return constraints


def _datetime_precision(type_: TypeEngine) -> int | None:
    """Return MySQL fractional-second precision, treating no fsp as zero.

    ``None`` means the reflected precision is not a valid MySQL fsp and can
    never match an expected column, so the caller reports a type mismatch.
    """
    fsp = getattr(type_, "fsp", None)
    if fsp is None or fsp == "":
        return 0
    try:
        precision = int(fsp)
    except (TypeError, ValueError):
        return None
    return precision if 0 <= precision <= 6 else None


def _type_signature(type_: TypeEngine) -> tuple[object, ...]:
    type_name = type(type_).__name__.upper()
    if type_name in {"INTEGER", "INT"}:
        return ("integer", bool(getattr(type_, "unsigned", False)))
    if type_name in {"STRING", "VARCHAR", "NVARCHAR"}:
        return ("string", getattr(type_, "length", None))
    if type_name == "TEXT":
        return ("text",)
    if type_name == "DATETIME":
        return ("datetime", _datetime_precision(type_))
    if type_name == "JSON":
        return ("json",)
    if type_name in {"NUMERIC", "DECIMAL"}:
        return (
            "numeric",
            getattr(type_, "precision", None),
            getattr(type_, "scale", None),
            bool(getattr(type_, "unsigned", False)),
        )
    return (type_name,)


def _normalize_server_default(value: object) -> str | None:
    """Normalize reflected and expected server defaults for comparison.

    MySQL reports string literals with their quotes and reports
    ``CURRENT_TIMESTAMP`` in several equivalent spellings. Some inspectors
    strip the quotes, so bare and quoted literals are normalized to the same
    case-sensitive literal form.
    """
    if value is None:
        return None

    arg = getattr(value, "arg", value)
    text = str(arg).strip()
    if not text or text.upper() == "NULL":
        return None

    if re.fullmatch(
        r"\(*\s*(?:CURRENT_TIMESTAMP|NOW)\s*(?:\(\s*\d*\s*\))?\s*\)*",
        text,
        re.IGNORECASE,
    ):
        return "CURRENT_TIMESTAMP"

    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        quote = text[0]
        return "literal:" + text[1:-1].replace(quote * 2, quote)

    # Treat an unquoted value as a literal too. This accepts inspectors that
    # strip quotes from string defaults while still comparing case-sensitively
    # and still rejecting unexpected expressions.
    return "literal:" + " ".join(text.split())


def _column_autoincrement(actual_column: dict[str, object]) -> bool:
    """Normalize reflected auto-increment flags to a boolean."""
    value = actual_column.get("autoincrement")
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "auto",
            "auto_increment",
        }
    return False


def _normalize_ondelete(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).upper().replace("_", " ").strip()
    if normalized in {"NO ACTION", "RESTRICT"}:
        return None
    return normalized


def _foreign_key_ondelete(foreign_key: dict[str, object]) -> str | None:
    options = foreign_key.get("options") or {}
    value = options.get("ondelete", foreign_key.get("ondelete"))
    return _normalize_ondelete(value)


def _foreign_key_target(foreign_key: dict[str, object]) -> tuple[str | None, tuple[str, ...]]:
    return (
        foreign_key.get("referred_table"),
        tuple(foreign_key.get("referred_columns") or ()),
    )


def _target_text(table: str, columns: tuple[str, ...]) -> str:
    return f"{table}({', '.join(columns)})"


def _foreign_key_matches(
    actual: dict[str, object],
    expected: _ForeignKeySpec,
) -> bool:
    expected_target = (expected.referred_table, expected.referred_columns)
    return (
        _foreign_key_target(actual) == expected_target
        and _foreign_key_ondelete(actual) == _normalize_ondelete(expected.ondelete)
    )


def _unique_column_sets(inspector: sa.Inspector, table_name: str) -> set[tuple[str, ...]]:
    unique_sets: set[tuple[str, ...]] = set()
    for constraint in inspector.get_unique_constraints(table_name) or ():
        columns = tuple(constraint.get("column_names") or ())
        if columns:
            unique_sets.add(columns)
    for index in inspector.get_indexes(table_name) or ():
        if index.get("unique"):
            columns = tuple(index.get("column_names") or ())
            if columns:
                unique_sets.add(columns)
    return unique_sets


def _inspect_existing_table(
    table: _TableSpec,
    inspector: sa.Inspector,
) -> tuple[list[str], list[_IndexSpec]]:
    problems: list[str] = []
    actual_columns = {
        column["name"]: column for column in inspector.get_columns(table.name)
    }

    for expected_column in table.columns:
        actual_column = actual_columns.get(expected_column.name)
        if actual_column is None:
            problems.append(
                f"{table.name}: missing column '{expected_column.name}'"
            )
            continue

        actual_type = actual_column.get("type")
        if (
            actual_type is None
            or _type_signature(actual_type)
            != _type_signature(expected_column.type_)
        ):
            problems.append(
                f"{table.name}: column '{expected_column.name}' has type "
                f"{actual_type!r}; expected {expected_column.type_!r}"
            )

        actual_nullable = actual_column.get("nullable")
        if actual_nullable is None or bool(actual_nullable) != expected_column.nullable:
            problems.append(
                f"{table.name}: column '{expected_column.name}' nullability is "
                f"{actual_nullable!r}; expected {expected_column.nullable}"
            )

        actual_default = actual_column.get("default")
        if _normalize_server_default(actual_default) != _normalize_server_default(
            expected_column.server_default
        ):
            problems.append(
                f"{table.name}: column '{expected_column.name}' server default is "
                f"{actual_default!r}; expected {expected_column.server_default!r}"
            )

        actual_autoincrement = _column_autoincrement(actual_column)
        if actual_autoincrement != expected_column.autoincrement:
            problems.append(
                f"{table.name}: column '{expected_column.name}' auto-increment is "
                f"{actual_column.get('autoincrement')!r}; "
                f"expected {expected_column.autoincrement}"
            )

    primary_key = inspector.get_pk_constraint(table.name) or {}
    actual_primary_key = tuple(primary_key.get("constrained_columns") or ())
    if actual_primary_key != table.primary_key:
        problems.append(
            f"{table.name}: primary key is {actual_primary_key}; "
            f"expected {table.primary_key}"
        )

    actual_unique_sets = _unique_column_sets(inspector, table.name)
    for expected_unique in table.unique_constraints:
        if expected_unique not in actual_unique_sets:
            problems.append(
                f"{table.name}: missing unique constraint on {expected_unique}"
            )

    actual_foreign_keys = inspector.get_foreign_keys(table.name) or []
    for expected_foreign_key in table.foreign_keys:
        matching = [
            foreign_key
            for foreign_key in actual_foreign_keys
            if tuple(foreign_key.get("constrained_columns") or ())
            == expected_foreign_key.columns
        ]
        if not matching:
            problems.append(
                f"{table.name}: missing foreign key on "
                f"{expected_foreign_key.columns} -> "
                f"{_target_text(expected_foreign_key.referred_table, expected_foreign_key.referred_columns)}"
            )
            continue

        for actual_foreign_key in matching:
            if not _foreign_key_matches(actual_foreign_key, expected_foreign_key):
                actual_target = _foreign_key_target(actual_foreign_key)
                problems.append(
                    f"{table.name}: foreign key on {expected_foreign_key.columns} "
                    f"targets {_target_text(actual_target[0] or '?', actual_target[1])} "
                    f"with ON DELETE {_foreign_key_ondelete(actual_foreign_key)!r}; "
                    f"expected "
                    f"{_target_text(expected_foreign_key.referred_table, expected_foreign_key.referred_columns)} "
                    f"with ON DELETE {_normalize_ondelete(expected_foreign_key.ondelete)!r}"
                )

    actual_indexes = {
        index.get("name"): index
        for index in inspector.get_indexes(table.name) or []
        if index.get("name") is not None
    }
    missing_indexes: list[_IndexSpec] = []
    for expected_index in table.indexes:
        actual_index = actual_indexes.get(expected_index.name)
        if actual_index is None:
            missing_indexes.append(expected_index)
            continue

        actual_columns = tuple(actual_index.get("column_names") or ())
        actual_unique = bool(actual_index.get("unique"))
        if actual_columns != expected_index.columns or actual_unique != expected_index.unique:
            problems.append(
                f"{table.name}: index '{expected_index.name}' is incompatible: "
                f"columns={actual_columns}, unique={actual_unique}; "
                f"expected columns={expected_index.columns}, "
                f"unique={expected_index.unique}"
            )

    return problems, missing_indexes


def _preflight_existing_tables(
    existing: set[str],
    inspector: sa.Inspector,
) -> dict[str, list[_IndexSpec]]:
    problems: list[str] = []
    missing_indexes: dict[str, list[_IndexSpec]] = {}

    for table in _TABLE_SPECS:
        if table.name not in existing:
            continue
        table_problems, table_missing_indexes = _inspect_existing_table(
            table, inspector
        )
        problems.extend(table_problems)
        if table_missing_indexes:
            missing_indexes[table.name] = table_missing_indexes

    if problems:
        details = "\n".join(f"- {problem}" for problem in problems)
        raise MigrationSchemaError(
            "Migration 20261110_0003 cannot continue because existing tables "
            "do not match the required schema. No existing table was altered. "
            "Review and repair the following manually, then rerun the "
            f"migration:\n{details}"
        )

    return missing_indexes


def _create_index(table_name: str, index: _IndexSpec) -> None:
    op.create_index(
        index.name,
        table_name,
        list(index.columns),
        unique=index.unique,
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = _existing_tables(inspector)
    missing_indexes = _preflight_existing_tables(existing, inspector)

    for table in _TABLE_SPECS:
        if table.name not in existing:
            continue
        for index in missing_indexes.get(table.name, ()):
            _create_index(table.name, index)

    for table in _TABLE_SPECS:
        if table.name in existing:
            continue
        op.create_table(
            table.name,
            *[_column_from_spec(column) for column in table.columns],
            *_constraints_from_spec(table),
        )
        for index in table.indexes:
            _create_index(table.name, index)


def downgrade() -> None:
    """Leave the legacy tables in place.

    These tables may have existed before this revision and may contain live
    data. Dropping them here would be destructive, so downgrade only changes
    Alembic's recorded revision.
    """
