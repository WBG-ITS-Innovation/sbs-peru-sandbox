"""Pytest configuration for the workflow-harness regression tests.

The repo is a uv workspace; dev dependencies (pytest, openai, python-dotenv,
gitpython, pyyaml) live in the root pyproject.toml's `dev` group. Run from
repo root:

    uv sync
    uv run pytest tests/

See docs/setup/uv-quickstart.md for the short tour.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Make scripts/ importable so the tests can pull functions out of close_prompt.py
# without running the script's argparse / sys.exit path.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
