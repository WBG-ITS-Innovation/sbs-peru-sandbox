# SPDX-License-Identifier: Apache-2.0
"""Every ORM model on disk must be registered in ``Base.metadata``.

``api/sbs_api/db/models/__init__.py`` eagerly imports each model module so
that (a) ``Base.metadata.create_all`` — which the ``db_schema`` test fixture
uses to provision the testcontainer — builds the *whole* schema, and (b)
Alembic's autogenerate sees the full metadata graph.

A model module that is never imported is invisible on both counts: its table
is missing from every test database, and an autogenerate run can emit a
migration that DROPs the live table because nothing in the metadata claims
it. Nine models drifted out of that ``__init__`` before this guard existed.

The check parses ``__tablename__`` straight from the source with ``ast`` so
it never depends on import order — the very thing it is guarding.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from sbs_api.db.base import Base
from sbs_api.db import models  # noqa: F401 — import for metadata side effects

MODELS_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "api"
    / "sbs_api"
    / "db"
    / "models"
)


def _tablenames_in(path: pathlib.Path) -> list[str]:
    """Return every ``__tablename__ = "literal"`` declared in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__tablename__":
                if isinstance(node.value, ast.Constant) and isinstance(
                    node.value.value, str
                ):
                    found.append(node.value.value)
    return found


def _model_modules() -> list[pathlib.Path]:
    return sorted(p for p in MODELS_DIR.glob("*.py") if p.name != "__init__.py")


def test_models_dir_is_discoverable():
    """Guard the guard: a bad path would make every assertion below vacuous."""
    assert MODELS_DIR.is_dir(), f"{MODELS_DIR} is not a directory"
    assert _model_modules(), "no model modules found — check MODELS_DIR"


@pytest.mark.parametrize(
    "module_path", _model_modules(), ids=lambda p: p.stem
)
def test_every_tablename_on_disk_is_registered(module_path: pathlib.Path):
    """Each ``__tablename__`` under db/models/ is in ``Base.metadata``.

    Failure means the module is missing from
    ``api/sbs_api/db/models/__init__.py``. Add the import there.
    """
    for tablename in _tablenames_in(module_path):
        assert tablename in Base.metadata.tables, (
            f"{module_path.name} declares __tablename__ = {tablename!r} but "
            f"that table is not in Base.metadata. Add an import for "
            f"sbs_api.db.models.{module_path.stem} to "
            f"api/sbs_api/db/models/__init__.py."
        )
