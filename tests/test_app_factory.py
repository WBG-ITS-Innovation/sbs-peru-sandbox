"""Application factory smoke tests.

No DB needed — these assert the FastAPI shape only.
"""

from __future__ import annotations


def test_create_app_returns_asgi_callable():
    from sbs_api.app import create_app

    app = create_app()
    # FastAPI is callable as an ASGI app (it is an instance of FastAPI which
    # implements `__call__` to be ASGI-callable).
    assert callable(app)


def test_auto_generated_openapi_disabled():
    from sbs_api.app import create_app

    app = create_app()
    assert app.openapi_url is None
    assert app.docs_url is None
    assert app.redoc_url is None


def test_canonical_yaml_route_registered():
    from sbs_api.app import create_app

    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/v1/openapi.yaml" in paths


def test_v1_prefix_enforced():
    from sbs_api.app import create_app

    app = create_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    # Every non-internal route lives under /v1.
    non_v1 = [p for p in paths if p and not p.startswith("/v1")]
    assert non_v1 == [], f"non-/v1 routes leaked: {non_v1}"
