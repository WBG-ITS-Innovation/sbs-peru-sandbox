# SPDX-License-Identifier: Apache-2.0
"""``python -m sbs_api`` entry point.

Runs uvicorn against the application factory. Read by ``scripts/run-api.sh``
in dev and by ``docker-compose.yaml`` for the in-container start command.

When ``SBS_API_MTLS_MODE=direct`` is set together with the three
``SBS_API_UVICORN_SSL_*`` env vars (populated by ``scripts/run-api.sh``
when ``dev-ca/`` is present), uvicorn binds with mTLS direct
termination and requires every client to present a cert signed by the
configured CA. This is the path the auth-chain smoke test
(``scripts/smoke-test-auth.sh``) exercises.
"""

from __future__ import annotations

import os
import ssl

import uvicorn


def main() -> None:
    host = os.environ.get("SBS_API_HOST", "0.0.0.0")
    port = int(os.environ.get("SBS_API_PORT", "8000"))
    reload = os.environ.get("SBS_API_RELOAD", "false").lower() == "true"

    ssl_kwargs: dict = {}
    if os.environ.get("SBS_API_MTLS_MODE", "disabled").lower() == "direct":
        ca_certs = os.environ.get("SBS_API_UVICORN_SSL_CA_CERTS")
        certfile = os.environ.get("SBS_API_UVICORN_SSL_CERTFILE")
        keyfile = os.environ.get("SBS_API_UVICORN_SSL_KEYFILE")
        if ca_certs and certfile and keyfile:
            ssl_kwargs = {
                "ssl_ca_certs": ca_certs,
                "ssl_certfile": certfile,
                "ssl_keyfile": keyfile,
                "ssl_cert_reqs": ssl.CERT_REQUIRED,
            }
        else:
            # mTLS mode declared but not configured — fail loud so a
            # mis-bootstrap doesn't silently start plain HTTP under a
            # security-claiming env var.
            missing = [
                name
                for name, value in (
                    ("SBS_API_UVICORN_SSL_CA_CERTS", ca_certs),
                    ("SBS_API_UVICORN_SSL_CERTFILE", certfile),
                    ("SBS_API_UVICORN_SSL_KEYFILE", keyfile),
                )
                if not value
            ]
            raise SystemExit(
                "SBS_API_MTLS_MODE=direct but missing required env vars: "
                + ", ".join(missing)
                + ". Run bash scripts/dev-ca.sh and re-run bash scripts/run-api.sh."
            )

    uvicorn.run(
        "sbs_api.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_level="info",
        **ssl_kwargs,
    )


if __name__ == "__main__":
    main()
