"""Authentication primitives — mTLS subject extraction, HMAC signing, OAuth.

The dependency wiring is in :mod:`sbs_api.dependencies`; this package
holds the pure-logic helpers (canonical-request construction, signature
computation, JWT issuance) the dependencies orchestrate.
"""
