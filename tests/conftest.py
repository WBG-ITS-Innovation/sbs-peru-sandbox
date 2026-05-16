"""Pytest configuration for the workflow-harness regression tests.

The application stack arrives in Part 3 with uv. Until then these tests cover
the harness scripts under scripts/. Run from repo root:

    pip install -r scripts/requirements-harness.txt
    pytest tests/
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Make scripts/ importable so the tests can pull functions out of close_prompt.py
# without running the script's argparse / sys.exit path.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
