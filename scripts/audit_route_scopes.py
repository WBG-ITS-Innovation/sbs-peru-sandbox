"""Route-scope audit (P-RESHAPE-6).

Enumerates every FastAPI route on the v1 app and classifies how it is
protected. A route is considered PROTECTED when at least one of its
dependencies is a recognised auth gate:

* ``verify_internal_secret``                 (internal shared-secret)
* ``requires_scope`` / ``requires_any_scope`` (persona RBAC, P-RESHAPE-5)
* ``require_any_role``                        (legacy role gate)
* an OAuth / mTLS / HMAC dependency           (institution edge)

Anything else must be explicitly listed in ``PUBLIC_ROUTES`` with a
rationale, or the ratchet test fails. The test
``tests/auth/test_all_routes_scoped.py`` reads :func:`audit_routes`.

Run directly to print the map:
    python scripts/audit_route_scopes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


# Auth-gate markers identified by the dependency callable's __qualname__.
# Factory-built closures are all named ``_checker`` but their qualname
# carries the factory (e.g. ``requires_scope.<locals>._checker``).
_AUTH_QUALNAME_SUBSTRINGS = (
    "verify_internal_secret",
    "requires_scope.<locals>",
    "requires_any_scope.<locals>",
    "require_any_role.<locals>",
    "require_scopes",          # OAuth scope dependency
    "_require_scopes",
    "verify_mtls",
    "MtlsValidated",
    "require_mtls",
    "verify_hmac",
    "hmac",
    "oauth",
    "get_current_client",
    "authorize",
)

# Routes that are deliberately public. Keyed by (method, path) with a
# rationale. Adding a public route is an explicit, reviewed act.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("GET", "/v1/health"): "Liveness probe — public by design.",
    ("GET", "/v1/health/live"): "K8s liveness probe.",
    ("GET", "/v1/health/ready"): "K8s readiness probe.",
    ("GET", "/v1/health/startup"): "K8s startup probe.",
    ("GET", "/v1/version"): "Build/version metadata — public.",
    ("GET", "/v1/openapi.yaml"): "Canonical OpenAPI contract — public per ADR 0027.",
    ("GET", "/v1/portal/"): "Developer portal (Stoplight) — public per ADR 0028.",
    ("GET", "/v1/portal/assets/{filename}"): "Portal static assets — public.",
    ("POST", "/v1/oauth/token"): "OAuth token endpoint — auth IS the endpoint.",
}


def _dependency_callables(dependant) -> list:
    """Recursively collect every dependency callable on a route."""
    out = []
    for dep in getattr(dependant, "dependencies", []):
        if getattr(dep, "call", None) is not None:
            out.append(dep.call)
        out.extend(_dependency_callables(dep))
    return out


def _is_protected(route) -> bool:
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return False
    callables = _dependency_callables(dependant)
    # Include the endpoint's own resolved sub-dependencies.
    for call in callables:
        qn = getattr(call, "__qualname__", "") or ""
        name = getattr(call, "__name__", "") or ""
        hay = f"{qn} {name}".lower()
        for marker in _AUTH_QUALNAME_SUBSTRINGS:
            if marker.lower() in hay:
                return True
    return False


def audit_routes() -> list[dict]:
    """Return one record per (method, path) route with its protection."""
    from sbs_api.app import create_app
    from sbs_api.config import get_settings

    app = create_app(settings=get_settings())
    records: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        if not path.startswith("/v1"):
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, path)
            if key in seen:
                continue
            seen.add(key)
            protected = _is_protected(route)
            public = key in PUBLIC_ROUTES
            records.append(
                {
                    "method": method,
                    "path": path,
                    "protected": protected,
                    "public": public,
                    "ok": protected or public,
                }
            )
    return sorted(records, key=lambda r: (r["path"], r["method"]))


def main() -> int:
    records = audit_routes()
    bad = [r for r in records if not r["ok"]]
    for r in records:
        flag = "OK " if r["ok"] else "!! "
        tag = "public" if r["public"] else ("scoped" if r["protected"] else "UNSCOPED")
        print(f"{flag}{r['method']:6} {r['path']:55} [{tag}]")
    print(f"\n{len(records)} routes, {len(bad)} unscoped-and-not-public")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
