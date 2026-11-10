"""Static/unit tests for migration 20261110_0003.

These tests deliberately do not import application settings, open ``.env``, or
connect to a database. They load the migration module directly, load the model
files with an isolated ``Base``, and replace Alembic's ``op`` object with an
in-memory recorder/inspector.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
from sqlalchemy.orm import DeclarativeBase

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "migrations" / "versions"
MODELS_DIR = BACKEND_DIR / "app" / "models"
MIGRATION_PATH = VERSIONS_DIR / "20261110_0003_legacy_core_tables.py"

MODEL_FILES = (
    ("_cp_review_department", "department.py"),
    ("_cp_review_incident", "incident.py"),
    ("_cp_review_citizen_report", "citizen_report.py"),
    ("_cp_review_incident_image", "incident_image.py"),
    ("_cp_review_status_history", "status_history.py"),
)

EXPECTED_TABLES = (
    "departments",
    "incidents",
    "citizen_reports",
    "incident_images",
    "status_history",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_20261110_0003", MIGRATION_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load migration: {MIGRATION_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_model_metadata():
    """Load the five models with an isolated Base, without importing settings."""

    class Base(DeclarativeBase):
        pass

    # The actor FK is declared as ``ForeignKey("users.id")`` without an
    # explicit type. Add the equivalent ``users.id`` shape so SQLAlchemy can
    # resolve the model FK type; this is not one of the five tables under test.
    sa.Table(
        "users",
        Base.metadata,
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
    )

    fake_app = types.ModuleType("app")
    fake_app.__path__ = []
    fake_database = types.ModuleType("app.database")
    fake_database.Base = Base

    previous_modules = {
        name: sys.modules.get(name) for name in ("app", "app.database")
    }
    loaded_modules: list[str] = []
    sys.modules["app"] = fake_app
    sys.modules["app.database"] = fake_database
    try:
        for module_name, filename in MODEL_FILES:
            spec = importlib.util.spec_from_file_location(
                module_name, MODELS_DIR / filename
            )
            if spec is None or spec.loader is None:
                raise AssertionError(f"Could not load model: {filename}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            loaded_modules.append(module_name)
            spec.loader.exec_module(module)
        return Base.metadata
    finally:
        for module_name in loaded_modules:
            sys.modules.pop(module_name, None)
        for name, previous_module in previous_modules.items():
            if previous_module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous_module


def _clone_schema(schema: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    cloned: dict[str, dict[str, object]] = {}
    for table_name, table_data in schema.items():
        cloned[table_name] = {
            "columns": [dict(column) for column in table_data["columns"]],
            "pk": {
                "constrained_columns": list(
                    table_data["pk"]["constrained_columns"]
                )
            },
            "unique_constraints": [
                {
                    "name": constraint.get("name"),
                    "column_names": list(constraint.get("column_names") or []),
                }
                for constraint in table_data["unique_constraints"]
            ],
            "indexes": [
                {
                    "name": index.get("name"),
                    "column_names": list(index.get("column_names") or []),
                    "unique": bool(index.get("unique")),
                }
                for index in table_data["indexes"]
            ],
            "foreign_keys": [
                {
                    "name": foreign_key.get("name"),
                    "constrained_columns": list(
                        foreign_key.get("constrained_columns") or []
                    ),
                    "referred_table": foreign_key.get("referred_table"),
                    "referred_columns": list(
                        foreign_key.get("referred_columns") or []
                    ),
                    "options": dict(foreign_key.get("options") or {}),
                }
                for foreign_key in table_data["foreign_keys"]
            ],
        }
    return cloned


def _reflected_server_default(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    if text.upper() in {
        "NOW",
        "NOW()",
        "CURRENT_TIMESTAMP",
        "CURRENT_TIMESTAMP()",
    }:
        return "CURRENT_TIMESTAMP"
    return text


def _schema_from_models(metadata: sa.MetaData) -> dict[str, dict[str, object]]:
    schema: dict[str, dict[str, object]] = {}
    for table in metadata.tables.values():
        if table.name not in EXPECTED_TABLES:
            continue
        columns = [
            {
                "name": column.name,
                "type": column.type,
                "nullable": column.nullable,
                "default": (
                    _reflected_server_default(column.server_default.arg)
                    if column.server_default is not None
                    else None
                ),
                # MySQL reflects True only for AUTO_INCREMENT columns and
                # False for non-incrementing integer columns.
                "autoincrement": column.autoincrement is True,
            }
            for column in table.columns
        ]
        unique_constraints = [
            {
                "name": constraint.name,
                "column_names": list(constraint.columns.keys()),
            }
            for constraint in table.constraints
            if isinstance(constraint, sa.UniqueConstraint)
        ]
        indexes = [
            {
                "name": index.name,
                "column_names": [column.name for column in index.columns],
                "unique": bool(index.unique),
            }
            for index in table.indexes
        ]
        foreign_keys = []
        for foreign_key in table.foreign_keys:
            referred_table, referred_column = foreign_key.target_fullname.split(
                ".", 1
            )
            foreign_keys.append(
                {
                    "name": foreign_key.constraint.name,
                    "constrained_columns": [foreign_key.parent.name],
                    "referred_table": referred_table,
                    "referred_columns": [referred_column],
                    "options": {"ondelete": foreign_key.ondelete},
                }
            )

        schema[table.name] = {
            "columns": columns,
            "pk": {
                "constrained_columns": list(table.primary_key.columns.keys())
            },
            "unique_constraints": unique_constraints,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
        }
    return schema


def _column_by_name(
    schema: dict[str, dict[str, object]],
    table_name: str,
    column_name: str,
) -> dict[str, object]:
    return next(
        column
        for column in schema[table_name]["columns"]
        if column["name"] == column_name
    )


class _FakeInspector:
    def __init__(self, schema: dict[str, dict[str, object]]) -> None:
        self._schema = schema

    def get_table_names(self) -> list[str]:
        return sorted(self._schema)

    def get_columns(self, table_name: str) -> list[dict[str, object]]:
        return self._schema[table_name]["columns"]

    def get_pk_constraint(self, table_name: str) -> dict[str, object]:
        return self._schema[table_name]["pk"]

    def get_unique_constraints(self, table_name: str) -> list[dict[str, object]]:
        return self._schema[table_name]["unique_constraints"]

    def get_indexes(self, table_name: str) -> list[dict[str, object]]:
        return self._schema[table_name]["indexes"]

    def get_foreign_keys(self, table_name: str) -> list[dict[str, object]]:
        return self._schema[table_name]["foreign_keys"]


class _FakeOp:
    def __init__(self) -> None:
        self.created_tables: list[sa.Table] = []
        self.created_indexes: list[tuple[str, str, tuple[str, ...], bool]] = []

    def get_bind(self) -> object:
        return object()

    def create_table(self, table_name: str, *args: object, **kwargs: object) -> None:
        # Building an in-memory Table validates column/constraint structure
        # without emitting DDL or touching a database.
        self.created_tables.append(sa.Table(table_name, sa.MetaData(), *args))

    def create_index(
        self,
        index_name: str,
        table_name: str,
        columns: list[str],
        *,
        unique: bool = False,
    ) -> None:
        self.created_indexes.append(
            (index_name, table_name, tuple(columns), unique)
        )


def _run_upgrade_capture(schema: dict[str, dict[str, object]]):
    module = _load_migration()
    fake_op = _FakeOp()
    inspector = _FakeInspector(schema)
    with (
        patch.object(module, "op", fake_op),
        patch.object(module.sa, "inspect", return_value=inspector),
    ):
        try:
            module.upgrade()
        except Exception as error:  # noqa: BLE001 - returned for assertions
            return module, fake_op, error
    return module, fake_op, None


def _run_upgrade(schema: dict[str, dict[str, object]]) -> _FakeOp:
    module, fake_op, error = _run_upgrade_capture(schema)
    if error is not None:
        raise error
    return fake_op


def _default_signature(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text in {"NOW()", "CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP()", "NOW"}:
        return "CURRENT_TIMESTAMP"
    return text


def _table_signature(table: sa.Table, module: object) -> dict[str, object]:
    columns: dict[str, tuple[object, ...]] = {}
    for column in table.columns:
        server_default = (
            _default_signature(column.server_default.arg)
            if column.server_default is not None
            else None
        )
        columns[column.name] = (
            module._type_signature(column.type),
            bool(column.nullable),
            server_default,
            column.autoincrement is True,
        )

    unique_constraints = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    indexes = {
        (
            index.name,
            tuple(column.name for column in index.columns),
            bool(index.unique),
        )
        for index in table.indexes
    }
    foreign_keys = {
        (
            foreign_key.parent.name,
            foreign_key.target_fullname,
            module._normalize_ondelete(foreign_key.ondelete),
        )
        for foreign_key in table.foreign_keys
    }
    return {
        "columns": columns,
        "primary_key": tuple(table.primary_key.columns.keys()),
        "unique_constraints": unique_constraints,
        "indexes": indexes,
        "foreign_keys": foreign_keys,
    }


def _spec_signature(spec: object, module: object) -> dict[str, object]:
    columns = {
        column.name: (
            module._type_signature(column.type_),
            column.nullable,
            _default_signature(column.server_default),
            column.autoincrement,
        )
        for column in spec.columns
    }
    indexes = {
        (index.name, index.columns, index.unique) for index in spec.indexes
    }
    foreign_keys = {
        (
            column,
            f"{foreign_key.referred_table}.{referred_column}",
            module._normalize_ondelete(foreign_key.ondelete),
        )
        for foreign_key in spec.foreign_keys
        for column in foreign_key.columns
        for referred_column in foreign_key.referred_columns
    }
    return {
        "columns": columns,
        "primary_key": spec.primary_key,
        "unique_constraints": set(spec.unique_constraints),
        "indexes": indexes,
        "foreign_keys": foreign_keys,
    }


class MigrationDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model_metadata = _load_model_metadata()
        cls.model_schema = _schema_from_models(cls.model_metadata)
        cls.model_tables = {
            table.name: table
            for table in cls.model_metadata.tables.values()
            if table.name in EXPECTED_TABLES
        }

    def test_revision_and_down_revision_are_exact(self) -> None:
        module = _load_migration()
        self.assertEqual(module.revision, "20261110_0003")
        self.assertEqual(module.down_revision, "20261108_0002")

    def test_there_is_exactly_one_alembic_head(self) -> None:
        metadata: dict[str, dict[str, object]] = {}
        for path in sorted(VERSIONS_DIR.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            values: dict[str, object] = {}
            for node in tree.body:
                if (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and node.target.id in {"revision", "down_revision"}
                ):
                    values[node.target.id] = ast.literal_eval(node.value)
            metadata[path.name] = values

        revisions = {
            values["revision"]
            for values in metadata.values()
            if "revision" in values
        }
        down_revisions: set[object] = set()
        for values in metadata.values():
            down_revision = values.get("down_revision")
            if isinstance(down_revision, str):
                down_revisions.add(down_revision)
            elif isinstance(down_revision, (list, tuple)):
                down_revisions.update(down_revision)

        self.assertEqual(revisions - down_revisions, {"20261110_0003"})
        self.assertEqual(
            metadata["20261108_0001_auth_foundation.py"],
            {"revision": "20261108_0001", "down_revision": None},
        )
        self.assertEqual(
            metadata["20261108_0002_status_history_actor.py"],
            {"revision": "20261108_0002", "down_revision": "20261108_0001"},
        )

    def test_preflight_specs_match_model_metadata(self) -> None:
        module = _load_migration()
        specs = {spec.name: spec for spec in module._TABLE_SPECS}

        self.assertEqual(set(specs), set(self.model_tables))
        for table_name, spec in specs.items():
            with self.subTest(table=table_name):
                self.assertEqual(
                    _spec_signature(spec, module),
                    _table_signature(self.model_tables[table_name], module),
                )

    def test_created_tables_match_model_metadata(self) -> None:
        module = _load_migration()
        fake_op = _run_upgrade({})
        created_tables = {
            table.name: table for table in fake_op.created_tables
        }
        created_indexes: dict[str, set[tuple[str, tuple[str, ...], bool]]] = {}
        for index_name, table_name, columns, unique in fake_op.created_indexes:
            created_indexes.setdefault(table_name, set()).add(
                (index_name, columns, unique)
            )

        self.assertEqual(set(created_tables), set(self.model_tables))
        for table_name, table in created_tables.items():
            with self.subTest(table=table_name):
                signature = _table_signature(table, module)
                signature["indexes"] = created_indexes.get(table_name, set())
                self.assertEqual(
                    signature,
                    _table_signature(self.model_tables[table_name], module),
                )

    def test_fresh_database_creates_all_five_tables_in_dependency_order(self) -> None:
        fake_op = _run_upgrade({})

        self.assertEqual(
            [table.name for table in fake_op.created_tables],
            list(EXPECTED_TABLES),
        )
        self.assertEqual(
            fake_op.created_indexes,
            [
                ("ix_citizen_reports_incident_id", "citizen_reports", ("incident_id",), False),
                ("ix_incident_images_incident_id", "incident_images", ("incident_id",), False),
                ("ix_status_history_incident_id", "status_history", ("incident_id",), False),
                (
                    "ix_status_history_changed_by_user_id",
                    "status_history",
                    ("changed_by_user_id",),
                    False,
                ),
            ],
        )

    def test_existing_complete_tables_are_not_modified(self) -> None:
        fake_op = _run_upgrade(_clone_schema(self.model_schema))

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_missing_tables_are_created(self) -> None:
        schema = _clone_schema(self.model_schema)
        for table_name in ("citizen_reports", "incident_images", "status_history"):
            schema.pop(table_name)

        fake_op = _run_upgrade(schema)

        self.assertEqual(
            [table.name for table in fake_op.created_tables],
            ["citizen_reports", "incident_images", "status_history"],
        )
        self.assertEqual(
            fake_op.created_indexes,
            [
                ("ix_citizen_reports_incident_id", "citizen_reports", ("incident_id",), False),
                ("ix_incident_images_incident_id", "incident_images", ("incident_id",), False),
                ("ix_status_history_incident_id", "status_history", ("incident_id",), False),
                (
                    "ix_status_history_changed_by_user_id",
                    "status_history",
                    ("changed_by_user_id",),
                    False,
                ),
            ],
        )

    def test_existing_incomplete_table_fails_before_any_ddl(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema.pop("incidents")
        schema["departments"]["columns"] = [
            column
            for column in schema["departments"]["columns"]
            if column["name"] != "description"
        ]

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn("departments", str(error))
        self.assertIn("missing column 'description'", str(error))
        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_missing_column_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["citizen_reports"]["columns"] = [
            column
            for column in schema["citizen_reports"]["columns"]
            if column["name"] != "transcript"
        ]

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn("citizen_reports", str(error))
        self.assertIn("missing column 'transcript'", str(error))
        self.assertEqual(fake_op.created_tables, [])

    def test_incorrect_column_type_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["departments"]["columns"][1]["type"] = sa.Text()

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn("departments: column 'name' has type", str(error))
        self.assertEqual(fake_op.created_tables, [])

    def test_incorrect_nullability_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["departments"]["columns"][2]["nullable"] = False

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "departments: column 'description' nullability",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])

    def test_matching_server_defaults_with_mysql_reflection_variants_are_accepted(
        self,
    ) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "status")["default"] = "'Submitted'"
        _column_by_name(schema, "incidents", "created_at")[
            "default"
        ] = "current_timestamp()"
        _column_by_name(schema, "citizen_reports", "created_at")[
            "default"
        ] = "CURRENT_TIMESTAMP(0)"
        _column_by_name(schema, "status_history", "changed_at")[
            "default"
        ] = "now()"

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_unquoted_and_text_clause_server_defaults_are_accepted(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "status")["default"] = "Submitted"
        _column_by_name(schema, "citizen_reports", "created_at")[
            "default"
        ] = sa.text("current_timestamp()")

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_incorrect_server_default_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "status")["default"] = "'Draft'"

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "incidents: column 'status' server default",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_missing_server_default_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "created_at")["default"] = None

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "incidents: column 'created_at' server default",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])

    def test_unexpected_server_default_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "departments", "name")["default"] = "'Unexpected'"

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "departments: column 'name' server default",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])

    def test_unexpected_current_timestamp_default_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "description")["default"] = sa.text(
            "CURRENT_TIMESTAMP"
        )

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "incidents: column 'description' server default",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_matching_autoincrement_flags_are_accepted(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "id")["autoincrement"] = True
        _column_by_name(schema, "incidents", "tracking_id")[
            "autoincrement"
        ] = False

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_mysql_autoincrement_reflection_variants_are_accepted(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "departments", "id")[
            "autoincrement"
        ] = "auto_increment"
        _column_by_name(schema, "incidents", "id")["autoincrement"] = 1
        _column_by_name(schema, "citizen_reports", "id")["autoincrement"] = "1"
        _column_by_name(schema, "incident_images", "id")["autoincrement"] = "yes"

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_missing_autoincrement_on_id_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "id")["autoincrement"] = False

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "incidents: column 'id' auto-increment",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])

    def test_unexpected_autoincrement_on_non_id_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "citizen_reports", "incident_id")[
            "autoincrement"
        ] = True

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "citizen_reports: column 'incident_id' auto-increment",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])

    def test_unexpected_autoincrement_on_non_integer_column_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "departments", "name")[
            "autoincrement"
        ] = "auto_increment"

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "departments: column 'name' auto-increment",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_datetime_zero_fractional_precision_is_accepted(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "created_at")[
            "type"
        ] = MySQLDateTime(fsp=0)
        _column_by_name(schema, "status_history", "changed_at")[
            "type"
        ] = MySQLDateTime()

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_datetime_fractional_precision_mismatch_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "created_at")[
            "type"
        ] = MySQLDateTime(fsp=6)

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "incidents: column 'created_at' has type",
            str(error),
        )
        self.assertIn("DATETIME", str(error))
        self.assertEqual(fake_op.created_tables, [])

    def test_datetime_string_zero_fractional_precision_is_accepted(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "incidents", "created_at")[
            "type"
        ] = MySQLDateTime(fsp="0")
        _column_by_name(schema, "citizen_reports", "created_at")[
            "type"
        ] = MySQLDateTime(fsp=None)

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_datetime_string_fractional_precision_mismatch_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        _column_by_name(schema, "status_history", "changed_at")[
            "type"
        ] = MySQLDateTime(fsp="3")

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "status_history: column 'changed_at' has type",
            str(error),
        )
        self.assertIn("fsp", str(error))
        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_missing_unique_constraint_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["incidents"]["unique_constraints"] = []

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "incidents: missing unique constraint on ('tracking_id',)",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])

    def test_incorrect_primary_key_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["departments"]["pk"]["constrained_columns"] = []

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn("departments: primary key is", str(error))
        self.assertEqual(fake_op.created_tables, [])

    def test_missing_required_index_is_created(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["citizen_reports"]["indexes"] = [
            index
            for index in schema["citizen_reports"]["indexes"]
            if index["name"] != "ix_citizen_reports_incident_id"
        ]

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(
            fake_op.created_indexes,
            [
                ("ix_citizen_reports_incident_id", "citizen_reports", ("incident_id",), False),
            ],
        )

    def test_missing_indexes_after_partial_failure_are_created(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["status_history"]["indexes"] = []

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(
            fake_op.created_indexes,
            [
                ("ix_status_history_incident_id", "status_history", ("incident_id",), False),
                (
                    "ix_status_history_changed_by_user_id",
                    "status_history",
                    ("changed_by_user_id",),
                    False,
                ),
            ],
        )

    def test_missing_foreign_key_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["citizen_reports"]["foreign_keys"] = []

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn("citizen_reports: missing foreign key", str(error))
        self.assertEqual(fake_op.created_tables, [])

    def test_incorrect_foreign_key_target_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["citizen_reports"]["foreign_keys"][0]["referred_table"] = "departments"

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn("citizen_reports", str(error))
        self.assertIn("targets departments(id)", str(error))
        self.assertIn("expected incidents(id)", str(error))
        self.assertEqual(fake_op.created_tables, [])

    def test_incorrect_on_delete_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        actor_foreign_key = next(
            foreign_key
            for foreign_key in schema["status_history"]["foreign_keys"]
            if foreign_key["constrained_columns"] == ["changed_by_user_id"]
        )
        actor_foreign_key["options"]["ondelete"] = "CASCADE"

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn("status_history", str(error))
        self.assertIn("ON DELETE 'CASCADE'", str(error))
        self.assertIn("expected users(id) with ON DELETE 'SET NULL'", str(error))
        self.assertEqual(fake_op.created_tables, [])

    def test_existing_compatible_indexes_are_accepted(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["citizen_reports"]["indexes"] = [
            {
                "name": "ix_citizen_reports_incident_id",
                "column_names": ["incident_id"],
                "unique": False,
            }
        ]

        fake_op = _run_upgrade(schema)

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_existing_incompatible_index_fails(self) -> None:
        schema = _clone_schema(self.model_schema)
        schema["citizen_reports"]["indexes"][0]["column_names"] = ["language"]

        module, fake_op, error = _run_upgrade_capture(schema)

        self.assertIsInstance(error, module.MigrationSchemaError)
        self.assertIn(
            "index 'ix_citizen_reports_incident_id' is incompatible",
            str(error),
        )
        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_downgrade_does_not_drop_or_alter_tables(self) -> None:
        module = _load_migration()
        fake_op = _FakeOp()
        with patch.object(module, "op", fake_op):
            module.downgrade()

        self.assertEqual(fake_op.created_tables, [])
        self.assertEqual(fake_op.created_indexes, [])

    def test_migration_has_no_destructive_or_application_imports(self) -> None:
        source = MIGRATION_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)

        forbidden_calls = {
            "drop_table",
            "drop_column",
            "drop_constraint",
            "drop_index",
            "alter_column",
            "rename_table",
            "execute",
            "bulk_insert",
        }
        found_calls = [
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in forbidden_calls
        ]

        self.assertEqual(found_calls, [])
        self.assertNotIn("Base.metadata", source)
        self.assertNotIn("create_all", source)
        self.assertNotIn("from app", source)
        self.assertNotIn("import app", source)
        self.assertNotIn("get_settings", source)
        self.assertNotIn(".env", source)


if __name__ == "__main__":
    unittest.main()
