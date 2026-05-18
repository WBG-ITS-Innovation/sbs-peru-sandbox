"""``python -m sbs_api`` entry point.

Runs uvicorn against the application factory. Read by ``scripts/run-api.sh``
in dev and by ``docker-compose.yaml`` for the in-container start command.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("SBS_API_HOST", "0.0.0.0")
    port = int(os.environ.get("SBS_API_PORT", "8000"))
    reload = os.environ.get("SBS_API_RELOAD", "false").lower() == "true"
    uvicorn.run(
        "sbs_api.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
