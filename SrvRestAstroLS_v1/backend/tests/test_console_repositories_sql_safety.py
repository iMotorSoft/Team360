import inspect
import re
from pathlib import Path

from modules.console import repositories
from modules.console.repositories import (
    PackageConsoleRepository,
    PermissionConsoleRepository,
    TaskConsoleRepository,
    WorkspaceConsoleRepository,
)

_REPOSITORY_CLASSES = (
    WorkspaceConsoleRepository,
    PermissionConsoleRepository,
    PackageConsoleRepository,
    TaskConsoleRepository,
)
_FORBIDDEN_SQL = re.compile(
    r"\b(?:insert|update|delete|alter|drop|truncate|create|grant|revoke)\b",
    re.IGNORECASE,
)


def _sql_constants():
    for repository_class in _REPOSITORY_CLASSES:
        for name, value in vars(repository_class).items():
            if name.endswith("_SQL"):
                yield repository_class.__name__, name, value


def test_repository_sql_constants_are_select_only():
    constants = list(_sql_constants())
    assert constants
    for class_name, name, sql in constants:
        assert sql.lstrip().lower().startswith("select"), f"{class_name}.{name}"
        assert not _FORBIDDEN_SQL.search(sql), f"{class_name}.{name}"


def test_repository_sql_is_parameterized():
    for class_name, name, sql in _sql_constants():
        if "%(" in sql:
            assert ")s" in sql, f"{class_name}.{name}"


def test_console_runtime_has_no_forbidden_data_layer_imports():
    module_dir = Path(inspect.getfile(repositories)).parent
    source = "\n".join(path.read_text() for path in module_dir.glob("*.py")).lower()
    forbidden = (
        "sql" + "alchemy",
        "sql" + "model",
        "async" + "pg",
        "pyd" + "antic",
        "base" + "model",
    )
    for name in forbidden:
        assert name not in source
