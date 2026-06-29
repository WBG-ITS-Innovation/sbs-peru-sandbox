# SPDX-License-Identifier: Apache-2.0
"""Every operation in the canonical OpenAPI spec has a registered FastAPI route.

Pairs with ``tests/test_openapi_pydantic_match.py`` to form a closed loop:
schema match (Pydantic ⇔ OpenAPI) plus surface match (routes ⇔ OpenAPI
operations).
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OPENAPI_PATH = REPO_ROOT / "api" / "openapi" / "sbs-api-v1.yaml"


@pytest.fixture(scope="module")
def openapi_spec() -> dict:
    return yaml.safe_load(OPENAPI_PATH.read_text())


@pytest.fixture(scope="module")
def app_routes() -> set[tuple[str, str]]:
    from sbs_api.app import create_app

    app = create_app()
    pairs: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path is None:
            continue
        for m in methods:
            if m == "HEAD":
                continue
            pairs.add((m.upper(), path))
    return pairs


def _spec_to_route_path(path: str) -> str:
    return "/v1" + path


def test_every_spec_operation_has_a_route(openapi_spec, app_routes):
    missing: list[str] = []
    for path, methods in openapi_spec["paths"].items():
        target = _spec_to_route_path(path)
        for verb, op in methods.items():
            if verb in {"parameters", "summary", "description"}:
                continue
            if not isinstance(op, dict):
                continue
            if (verb.upper(), target) not in app_routes:
                missing.append(f"{verb.upper()} {target} (operationId={op.get('operationId')!r})")
    assert not missing, "spec operations without a FastAPI route: " + "; ".join(missing)


def test_canonical_yaml_route_is_registered(app_routes):
    assert ("GET", "/v1/openapi.yaml") in app_routes


def test_auto_generated_openapi_paths_are_absent(app_routes):
    # The contract is the YAML, not FastAPI's reflection.
    auto_paths = {("GET", "/openapi.json"), ("GET", "/docs"), ("GET", "/redoc")}
    assert auto_paths.isdisjoint(app_routes)
