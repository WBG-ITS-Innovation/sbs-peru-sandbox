# ADR 0030 — Health probe semantics

- **Status:** Accepted
- **Date:** 2026-05-18
- **Target prompt / Part:** Prompt 6 / Part 2
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

Prompt 6 lands the FastAPI runtime that ships to Kubernetes once Part 9
adds the Helm chart. Kubernetes distinguishes three probe semantics
(liveness, readiness, startup) and a service that conflates them paints
itself into corners: a process whose database connection blips for one
second should not be restarted by the orchestrator; a process still
applying migrations should not be sent traffic. The probe shapes need to
match Kubernetes' model exactly, so when the chart lands the probe URLs
drop in without re-design.

## Decision

Three probes with explicit semantics.

**`GET /v1/health/live`** — *process responsiveness*. No I/O. Always 200
unless the process is dying. The orchestrator's restart policy reads
this; a failing live probe means "kill and re-create the pod." Liveness
must not depend on the database because a transient DB failure must not
cause a pod restart loop.

**`GET /v1/health/ready`** — *traffic readiness*. Performs a DB ping
(`SELECT 1`, asyncio timeout 200ms) and caches the result for 1 second.
Returns 200 if the DB was reachable within the last 1s window; 503 with
ProblemDetail if the most recent ping failed. Used by the load balancer
to decide whether to send traffic.

  *The cache window is load-bearing.* Without it a 200ms DB flap that
  coincides with the readiness probe interval would mark every pod
  not-ready simultaneously; with it, the flap is absorbed.

  *Operational rule (flagged for SBS):* flaps are *alerted*, not
  auto-remediated. DB flaps cannot be fixed by restarting API pods.

**`GET /v1/health/startup`** — *startup completion*. Confirms the
`alembic_version` row exists (migrations applied). 200 once, 503 until
then. Used by the orchestrator's startup probe, which has a longer
timeout than liveness so a slow migration doesn't trigger pod-restart
during deployment.

**DB-ping shape.** `SELECT 1`. Not write capability, not replication
lag. The May 25 architecture is single-primary; replication-lag checks
are a Part 9 decision when read replicas are added.

**ProblemDetail on 503.** Same envelope as every other error: stable
code `SBS-503-001` (service unavailable) on a generic readiness failure,
`AUTH_NOT_CONFIGURED` (`SBS-503-002`) when auth has not been wired.

## Precedent

The three-probe model is the Kubernetes Pattern. See the upstream
documentation:
[*Configure Liveness, Readiness and Startup Probes*](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
— Kubernetes documentation, section "When should you use a startup
probe?" and "Define readiness probes."

The DB-ping-with-cache pattern is the documented posture for AWS RDS
ProxySQL probes and is similarly used by every major Go web framework's
health package (e.g., `heptiolabs/healthcheck`).
[docs/research/market-comparators.md §5.A](../research/market-comparators.md#5a-api-and-schema-layer)'s
standards-pack table includes a `/v1/health` endpoint as one of the
artifacts regulators publish; the three-probe decomposition is the
production-grade refinement.

## Divergence

We diverge from the FastAPI default of "single `/health` returning
overall status." The single endpoint is sufficient for a private
internal API; for a regulator-grade service running in Kubernetes the
three-probe decomposition is the right model.

We diverge from "ready means write-capable." Write-capability checks
require an actual write (e.g., `INSERT ... RETURNING`) which has a
non-trivial DB cost when probes run every few seconds across replicas.
The May 25 architecture is single-primary; a `SELECT 1` is the correct
shape until the architecture diverges from that.

We diverge from "no cache window — every probe issues a DB ping." The
cache window absorbs sub-second DB flaps without dropping pods from the
load balancer. The window is configurable
(`SBS_API_READINESS_CACHE_SECONDS`) so an operations team that
preferred per-probe pings can disable the cache. The default is on.

## Consequences

- The Helm chart in Part 9 maps the three probes to the matching
  Kubernetes probe types with the correct timeouts. The chart will
  reference this ADR.
- The cache window is global to the process (a module-level variable in
  `routes/meta.py`). Tests that need to control the cache call
  `_reset_ready_cache_for_test()` between phases. The function is
  underscore-prefixed because production code does not need it.
- The startup probe checks for the *presence* of any `alembic_version`
  row, not for *the exact head revision*. Checking for the exact head is
  attractive but binds the running container to one specific migration
  state; a follow-up migration that ran out-of-band (e.g., a hotfix DDL)
  would cause the probe to flap. Presence + the migration's invariant
  that `alembic_version` is only updated by `alembic upgrade` is the
  right test. The exact-head check can land in Part 9 if operators
  decide the trade-off is worth it.
- The 503 ProblemDetail body on readiness failure includes a
  human-readable `detail` ("Database ping failed within the cache
  window") so a curl against `/v1/health/ready` from an operator gives a
  reason without needing to read logs.
- The 1-second cache window is the smallest value that absorbs a
  single-cycle DB flap on most orchestrator probe schedules (which
  default to 10 seconds and probe every 5–10 seconds). Cross-review
  pushed back on whether 1s is correct; the reply is "1s is the
  smallest value with a useful effect, and the cache is configurable
  away if the operator disagrees."
