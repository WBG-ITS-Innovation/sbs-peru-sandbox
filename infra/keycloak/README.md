# Keycloak sandbox IdP — supervisor UI

This directory holds the Keycloak realm that backs the supervisor UI's
OAuth login flow. The realm is the **sandbox** identity provider; the
production overlay federates with whatever SSO SBS already operates and
does not use this realm.

## What's here

```
infra/keycloak/
├── README.md                       (this file)
├── realm-sbs-demo.json             (the realm export — source of truth)
└── export-realm.sh                 (regenerate the JSON from a running container)
```

The realm carries:

- One client: `sbs-supervisor-ui` (public, PKCE-required, S256, redirect
  URIs for `:3000/app/auth/callback` and `:8000/app/auth/callback`).
  `directAccessGrantsEnabled: true` for the demo-mode persona switcher
  (ADR 0040 §D8); production overlay disables it.
- Three users with seeded passwords (sandbox-only — see warning below).
- Three realm-roles: `sbs:conduct:supervisor`, `sbs:conduct:analyst`,
  `sbs:conduct:head`. One per user.
- Brute-force protection enabled (default settings).
- Locale: Spanish primary, English secondary.

## How it gets loaded

The `keycloak` service in `docker-compose.yaml` mounts this directory at
`/opt/keycloak/data/import/` and runs `start-dev --import-realm` (the
Keycloak 22+ `--import-realm` flag). The realm is loaded as part of the
container's normal startup, in the same lifecycle phase as Keycloak's
internal realm initialisation — there is no race between an init-script
and the readiness check.

The alternative — an init-script that hits the admin API after Keycloak
reports ready — was ruled out by ADR 0040 §D6 because of intermittent
cold-start failures on certain hardware.

## Sandbox credentials (NOT secrets)

The realm contains three deliberately-stable demo passwords so the
narrator can sign in during the live demo without consulting a vault:

| User | Password |
| --- | --- |
| `supervisor@sandbox.example.com` | `supervisor-demo-2026` |
| `analyst@sandbox.example.com` | `analyst-demo-2026` |
| `unit-head@sandbox.example.com` | `unit-head-demo-2026` |

These are **sandbox-only** credentials. The Keycloak service in
`docker-compose.yaml` is the dev/demo IdP; production deploys against
SBS's actual SSO. These passwords never reach a production realm.

## How to re-export

If you edit the realm via the Keycloak admin UI (http://localhost:8081,
admin / admin) and want to capture the change, run:

```bash
bash infra/keycloak/export-realm.sh
```

The script:

1. `docker compose exec keycloak ...` invokes the Keycloak `kc.sh` CLI
   inside the running container to export the realm to a temp file.
2. Copies the export back out via `docker compose cp`.
3. Pretty-prints with `jq` and writes over `realm-sbs-demo.json`.
4. Strips environment-specific cruft (timestamps, container ids) that
   would otherwise churn the diff on every export.

The exported JSON is committed; the in-memory state of a running
container is not the source of truth.

## Production overlay

Production lands in Part 9 (Helm). The overlay differs from this
sandbox realm in:

- The realm itself is **not** `sbs-demo`; the agency's own realm is
  federated, or the supervisor UI is re-pointed at the agency IdP.
- `directAccessGrantsEnabled` on the client is **false**. The
  demo-mode persona switcher is not available in production.
- Demo users do not exist. Real users come from the agency's user
  directory (LDAP / federation / SAML).
- TLS is required (`sslRequired: all`); the sandbox sets `external`
  for dev convenience.
- Brute-force protection thresholds match the agency's auth policy.

The Helm chart's values file is the right place to encode these. The
realm JSON in this directory is the dev/demo source of truth only.

## Local bring-up (after reboot or fresh clone)

1. `bash scripts/dev-up.sh`          — postgres+redis, migrations, seeds
2. `bash scripts/run-api.sh`          — API on :8000 (own terminal)
3. `cd app && npm run build && npm run start -- --hostname localhost`   — UI on :3000 (own terminal)
4. `bash scripts/demo.sh --scale small`   — demo data
5. Login at http://localhost:3000 → "Enter evaluation sandbox"

**Keycloak note:** any change to realm-sbs-demo.json requires wiping the volume
(`docker compose stop keycloak && docker compose rm -f keycloak && docker volume rm
sbs-suptech-prototype_sbs_keycloak_data && docker compose up -d keycloak`) — the
import strategy is IGNORE_EXISTING and silently skips if the realm already exists.
The Keycloak healthcheck reports "unhealthy" falsely; verify with
`curl localhost:8081/realms/sbs-demo/.well-known/openid-configuration` instead.