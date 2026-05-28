"""Route-scope ratchet (P-RESHAPE-6).

Enumerates every v1 FastAPI route and asserts each is either protected
by a recognised auth gate OR explicitly listed in the PUBLIC_ROUTES
allowlist. This is the gate that stops a new route being added without
a scope tag.

No DB required — the audit constructs the app and inspects route
dependency graphs.
"""

from __future__ import annotations

from scripts.audit_route_scopes import PUBLIC_ROUTES, audit_routes


def test_every_route_is_scoped_or_public():
    records = audit_routes()
    assert records, "expected the app to expose v1 routes"
    unprotected = [
        f"{r['method']} {r['path']}" for r in records if not r["ok"]
    ]
    assert not unprotected, (
        "these routes are neither scope-protected nor in the PUBLIC_ROUTES "
        f"allowlist: {unprotected}"
    )


def test_public_allowlist_entries_still_exist():
    """A PUBLIC_ROUTES entry that no longer maps to a real route is dead
    config — fail so the allowlist stays honest."""
    records = audit_routes()
    live = {(r["method"], r["path"]) for r in records}
    stale = [key for key in PUBLIC_ROUTES if key not in live]
    assert not stale, f"PUBLIC_ROUTES has stale entries: {stale}"


def test_new_persona_surfaces_are_protected():
    """Spot-check that the P-RESHAPE-5/6 surfaces resolve as protected."""
    records = {(r["method"], r["path"]): r for r in audit_routes()}
    for key in (
        ("GET", "/v1/internal/ops/social_health"),
        ("GET", "/v1/internal/exec/sector_broadcasts"),
        ("POST", "/v1/internal/sector_broadcast/{broadcast_id}/approve_primary"),
        ("POST", "/v1/internal/sector_broadcast/{broadcast_id}/approve_secondary"),
    ):
        assert key in records, f"missing route {key}"
        assert records[key]["protected"], f"{key} not protected"
