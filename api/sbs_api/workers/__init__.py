"""arq worker entry points (Prompt 8, ADR 0034).

The batch worker drains ``process_batch`` jobs queued by the
``POST /v1/batches`` endpoint. Workstream D extends the same worker
process with ``deliver_webhook`` for outbound HMAC-signed callbacks.

Run the worker:

    uv run arq sbs_api.workers.batch_worker.WorkerSettings

The docker-compose ``worker`` service uses the same command.
"""

from sbs_api.workers.arq_pool import (
    enqueue_job,
    get_arq_pool,
    reset_arq_pool_for_test,
)

__all__ = [
    "enqueue_job",
    "get_arq_pool",
    "reset_arq_pool_for_test",
]
