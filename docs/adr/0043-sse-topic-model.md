# ADR 0043 — SSE topic model and role scoping

- **Status:** Accepted
- **Date:** 2026-05-22
- **Target prompt / Part:** Prompt 10 / Part 8
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The supervisor UI surfaces live updates via Server-Sent Events. ADR 0040 §D5 pinned the refresh contract (snapshot + delta + `Last-Event-ID` replay) before the implementation; this ADR documents the topic model that landed across WS3 (cockpit), WS4 (findings), and WS5 (approvals). The ADR is partly retroactive — the implementation has been in place since the WS3 SSE infrastructure commit — but the contract was deferred to here so the topic shape, role scoping, and operational characteristics could be locked in one document.

Four questions interact:

1. **Topic granularity.** One firehose topic per cockpit/findings/approvals, or fine-grained topics per institution / per role / per scope.
2. **Role scoping.** Who may subscribe to which topic; what enforcement layer is the gate.
3. **Buffer and replay.** Ring-buffer size + retention, the `Last-Event-ID` resumption contract from ADR 0040.
4. **Operational scale.** In-memory pub/sub versus Redis Streams; what production needs that the demo does not.

## Decision

### D1 — Three topics: `cockpit`, `findings`, `approvals`

The supervisor UI subscribes to exactly three topics:

| Topic | What it carries |
| --- | --- |
| `cockpit` | `complaint.received` (Tier 1 / Tier 2 arrivals), `anomaly.detected`, `signal.threshold.crossed`. |
| `findings` | `complaint.received`, `narrative.edited`, `finding.published`. |
| `approvals` | `approval.pending` (a row landed in `pending_approvals`), `approval.decided` (any of the four decisions). |

Single-stream-per-topic. The same `useSSE(topic)` hook from WS3 consumes any of them. Fine-grained per-institution or per-role topics were considered and ruled out — the role check is enforced at subscription time (D2), and the volume on the demo path does not justify the operational cost of additional streams.

### D2 — Role scoping at subscription time, declarative map

The `/v1/internal/sse/{topic}` route checks `X-SBS-Role` against a per-topic required-role set before opening the stream. Subscribers without a matching role receive 403; the stream never opens. The current map:

| Topic | Required roles (any of) |
| --- | --- |
| `cockpit` | supervisor, analyst, head |
| `findings` | supervisor, analyst, head |
| `approvals` | analyst, head (supervisor scope alone is denied) |

The supervisor scope's exclusion from `approvals` matches ADR 0040 §D7's demo outline — the production role model maps to SBS's actual org chart (segment-level scoping, maker/checker chains) and lifts this table to a configuration layer. For Prompt 10 the map sits in `api/sbs_api/routes/sse.py:_TOPIC_ROLES` as the source of truth.

Per-event content filtering inside a stream — supervisor-scoped institution filtering on the `findings` topic, for example — is **not** implemented in Prompt 10. The supervisor subscribes successfully and receives every event for which the topic is open; the institution scoping happens at the GET endpoint that lists findings. Stream-level filtering is the production deliverable (Part 8); the contract supports it without requiring a redesign (the subscriber's role set is available in the request handler).

### D3 — In-memory ring buffer (500 events / topic), `Last-Event-ID` replay

Each topic owns a 500-event ring buffer (`api/sbs_api/sse/manager.py:_RING_BUFFER_SIZE`). On reconnect, `Last-Event-ID: N` replays events with id > N from the buffer; if the buffer has aged past N (the operator was offline long enough that the missed window evicted), the server emits `event: resync-required` and the client refetches the snapshot. The contract is the WHATWG EventSource spec applied to the bus pattern.

500 events is ~30 minutes of demo-scale activity. Larger windows are deferred to the production-scale design.

### D4 — Heartbeat 25s, snapshot-then-delta protocol

Each connection emits an SSE-comment heartbeat every 25 seconds so HTTP proxies do not idle the connection out (most defaults are 30–60s). On fresh connect (no `Last-Event-ID`), the server emits one `event: snapshot` with `id: 0` carrying the full topic state, then streams `event: <name>` deltas with monotonic `id:` per topic. Clients treat snapshot events as already-applied (id ≤ 0); delta events update the local state.

### D5 — Close-on-token-expiry, refresh-and-reconnect on the client side

When the session's access token expires mid-stream:

1. The server terminates the stream with a final `event: session-expired` event carrying a transient correlation id.
2. The client (the `useSSE` hook) catches the disconnect and issues a silent refresh via `POST /api/auth/refresh`. The session's refresh token is held server-side (ADR 0040 §D3); the browser never touches it.
3. On successful refresh the client reconnects with `Last-Event-ID`; the server replays from the ring buffer.
4. On refresh failure (refresh token expired, IdP unreachable) the client redirects to `/app/login`.

The session-expired path is the integration between the auth chain (ADR 0040) and the SSE chain (this ADR); the contract was pinned in ADR 0040 §D5 before either implementation landed.

### D6 — Reconnect backoff: 1s → 30s exponential

The client's `useSSE` hook uses exponential backoff with a 1-second initial delay doubling to a 30-second ceiling, restarting at 1 second on the next successful connect. The 25s heartbeat falls within the 30s ceiling so a healthy connection's silence does not look like a failure.

## Precedent

- [market-comparators.md §5.A.M.U "Supervisor-side user session auth" — SSE auth refresh paragraph](../research/market-comparators.md#5amu-supervisor-side-user-session-auth-added-prompt-10-for-adr-0040) — the load-bearing reference. The paragraph cites the WHATWG EventSource specification's `Last-Event-ID` resumption mechanism, GitHub Actions log streaming, and Stripe CLI event tail as the canonical pattern this ADR adopts. ADR 0040 §D5 pinned the refresh contract; this ADR adopts and extends it to per-topic scoping + the topic enumeration.
- **WHATWG EventSource specification** — the wire format (`id:` / `event:` / `data:` line shape + blank-line termination + comment heartbeats).
- **Redis Streams documentation** — referenced as the production substrate per the Divergence section.

## Divergence

- **In-memory bus in Prompt 10; Redis Streams in production.** The OAuth BCP and EventSource spec do not prescribe a backend; the in-memory choice fits demo single-instance scale. Production with multiple supervisor-UI replicas needs Redis Streams (or NATS, or an equivalent durable pub/sub) so a publish from any replica reaches subscribers on every replica. The `SSEBus` interface in `api/sbs_api/sse/manager.py` does not change at that migration — `publish()` and `subscribe()` are the same shape against Redis-backed state. Part 9 deliverable.
- **Per-subscriber content filtering deferred.** The role gate is currently topic-level (subscribe / 403). Production needs per-event filtering so a supervisor's findings topic does not stream events for institutions outside her scope. The architectural hook is in place (the subscriber's `granted_roles` is available); the filter is the implementation work.
- **No exactly-once delivery.** A slow subscriber's queue can fill (`asyncio.Queue` `put_nowait` raises `QueueFull`) and the bus drops the event for that subscriber. The `Last-Event-ID` reconnect is the recovery. This matches the at-most-once semantics SSE assumes; the alternative (block publishers on slow subscribers) is worse for the demo's perceived liveness.

## Consequences

**Locks in.**

- The three-topic model. New topics require an ADR amendment.
- The role map. Production may grow it (e.g., per-institution sub-topics for federation between supervisory units), but the supervisor's exclusion from approvals is the documented contract for demo.
- The 500-event buffer + `Last-Event-ID` replay + 25-second heartbeat + 1s→30s exponential backoff. Tuning any of these requires a benchmark + amendment.
- The session-expired → silent-refresh → reconnect-with-Last-Event-ID flow as the integration seam between auth and SSE.

**Leaves open.**

- Redis Streams migration for multi-replica scale (Part 9).
- Per-subscriber content filtering for supervisor-scoped findings (Part 8).
- Optional `Cache-Control: no-store` + `X-Accel-Buffering: no` headers — already in place but proxy behaviour varies; verify on the production overlay.
- WebSocket as an alternative to SSE — not required for the demo's read-only model.

**Trail.** ADR 0040 §D5 pinned the refresh contract; this ADR documents the topic model that landed in the WS3 SSE infrastructure commit, the WS4 SSE topic extension for findings + approvals, the WS5 approvals `approval.decided` publish, and the WS7 reconnect-replay test.
