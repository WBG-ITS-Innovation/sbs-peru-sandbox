# Demo personas

The SupTech cockpit is exercised by five SBS-side personas. Each maps to
one Keycloak realm role (`X-SBS-Role` in code) and one fixed scope set.
Three names (Lucía, María, Sergio) are **archetypes**, not real people.
Two — **Jorge** and **Rosa** — replaced earlier placeholders that
collided with real SBS staff names (P-RESHAPE-8.6).

| Persona | Display name | Role string | Stub id | What they do |
|---|---|---|---|---|
| Analyst | Lucía Ramos | `sbs:conduct:analyst` | `lucia` | Inspect individual complaints; model internals; corpus search |
| Supervisor | María Lazo | `sbs:conduct:supervisor` | `maria` | Pattern landscape for assigned institutions; approve FIBriefs |
| Unit Head | Jorge Caballero | `sbs:conduct:head` | `jorge` | All patterns; final approval + override authority; audit |
| Superintendent | Sergio Velarde | `sbs:superintendent` | `sergio` | Executive aggregates only — NO per-complaint data, NO raw narrative |
| SBS IT | Rosa Salazar | `sbs:sbs_it` | `rosa` | Platform operations telemetry only — NO business data of any kind |

See [superintendent.md](superintendent.md) for the one deliberate
write exception (sector-broadcast co-approval).

## What each persona can DO (action surface)

Beyond what they *see*, each persona has a small set of action verbs so
no dashboard is read-only (P-RESHAPE-8.5 / 8.6 / 9). `GET
/v1/internal/cockpit/actions` returns the caller's set; the action
registry is locked in code (`api/sbs_api/personas/action_registry.py`).

| Persona | Actions |
|---|---|
| Analyst (Lucía) | Propose pattern · Flag complaint for review · Request enrichment |
| Supervisor (María) | Approve FI brief · Delegate pattern to analyst · Defer pattern |
| Unit Head (Jorge) | Override supervisor decision · Approve sector broadcast (primary) · Generate weekly digest |
| Superintendent (Sergio) | Co-approve sector broadcast (secondary) · Request deeper look · Sign weekly digest |
| SBS IT (Rosa) | Annotate incident · Retry failed webhook · Requeue agent run · Circuit-break FI ingestion |

The SBS IT remediation actions (retry / requeue / circuit-break) are
high-privilege: they require the `ops:remediate` scope, carry a rationale
(50 chars for circuit-break), and land an `incident_annotations` audit
row. Circuit-breaking PAUSEs ingestion for one institution — a paused FI
gets `503 fi_circuit_breaker_paused` until SBS resumes it.

## Logging in as a persona (real path)

In a full demo the Next.js BFF authenticates against Keycloak
(`infra/keycloak/realm-sbs-demo.json`, realm `sbs-demo`) and forwards the
caller's role on the `X-SBS-Role` header. Demo passwords are
`<persona>-demo-2026`, e.g. `jorge-demo-2026`.

## The dev auth stub (no Keycloak needed)

For local rehearsal you can skip Keycloak entirely. When **both**
`SBS_API_AUTH_STUB_ENABLED=true` and `SBS_API_ENVIRONMENT=dev`, the API
accepts a deliberately non-standard token:

```
Authorization: Bearer stub:<persona_id>
```

where `<persona_id>` is one of `lucia`, `maria`, `jorge`, `sergio`,
`rosa`. The token resolves to that persona's role and exact scope set —
the same scope checks the real JWT path enforces. Every use emits a
WARNING log line, and an unknown persona returns 401.

This stub is **gated on both flags** and is ignored entirely in any
other configuration. A `stub:` token is never honoured in staging or
prod; the production JWT / Keycloak path is unchanged. The non-standard
`stub:` prefix makes its use obvious in logs.

### Quick check

```bash
# Jorge holds agents:read → 200
curl -H "Authorization: Bearer stub:jorge" \
  http://localhost:8000/v1/internal/cockpit/agents/divalevale/activity

# Sergio holds no institution complaints scope → 403 (scope enforced)
curl -H "Authorization: Bearer stub:sergio" \
  http://localhost:8000/v1/complaints
```

A full per-persona walkthrough lives in
[scripts/demo-curl-examples.sh](../../scripts/demo-curl-examples.sh).
