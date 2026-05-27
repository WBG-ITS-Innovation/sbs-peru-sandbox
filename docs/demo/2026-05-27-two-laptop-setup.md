# Two-laptop sandbox demo — operator setup

This document tells an operator how to wire two laptops together for
the live SBS sandbox demo: one laptop runs the API + supervisor UI as
the "SBS side", the other runs the institution sender as the "bank
side". The two laptops can be on a phone hotspot, a hotel network, or
a wired LAN — the only requirement is that they reach each other on
TCP/IP.

If you are demoing on a single laptop, ignore this file and follow
the regular `README.md` quickstart.

## What the demo proves

* An institution pushes Annex 1-A complaints to the SBS sandbox API
  over the production-shaped auth chain (OAuth client_credentials +
  HMAC SHA-256 + Idempotency-Key + mTLS or dev-XFCC).
* Each submission goes through schema validation → taxonomy
  normalization → PII redaction → canonical persistence → Annex 1-A
  data-quality checks → audit chain → cockpit SSE delta.
* The supervisor cockpit on the SBS laptop shows the new cards
  within ~5 seconds of the institution sending them.
* Surface forms differ by institution (`"Página web de la empresa"`
  on Banco1, `"PAG. WEB DE LA EMPRESA"` on Banco3) and converge on
  the same canonical code (`pagina_web`).

## Roles

* **Laptop A — SBS side.** Runs Postgres + Redis + the FastAPI
  service on port 8000 and the Next.js supervisor UI on port 3000.
* **Laptop B — institution side.** Runs the ingestion CLI
  (`scripts/ingest_sample_dataset.py`) which reads the real Annex 1-A
  sample (`data/sbs_sample/SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx`) and
  posts to laptop A's API. No database, no UI.

A single repo checkout works for both roles. The CLI does not need
the database — only the `dev-ca/` cert bundle for mTLS / dev-XFCC.

## Network requirements

* Both laptops on the same network. A phone hotspot is fine; most
  hotel networks are not (they isolate clients). Test
  `ping <laptop-A-ip>` from laptop B before starting.
* No firewall rules blocking TCP 8000 (API) or TCP 3000 (UI). On
  macOS, run `sudo /usr/libexec/ApplicationFirewall/socketfilterfw
  --setglobalstate off` for the demo if the firewall is on; restore
  after.

## Step 1 — find laptop A's LAN IP

On macOS (laptop A):

```bash
ipconfig getifaddr en0          # Wi-Fi
ipconfig getifaddr en1          # second Wi-Fi or wired
```

Example output: `192.168.43.137`. Use that IP wherever this doc
writes `<LAPTOP_A_IP>`.

On Linux:

```bash
ip -4 addr show scope global | awk '/inet / {print $2}' | head -1
```

## Step 2 — boot the SBS side (laptop A)

```bash
bash scripts/dev-up.sh                 # Postgres + Redis + migrations + seeds
SBS_API_MTLS_MODE=proxy \
  bash scripts/run-api.sh              # uvicorn binds 0.0.0.0:8000

# in a second terminal
cd app && npm run dev                  # next dev binds 0.0.0.0:3000
```

The default `cors_allow_origins` accepts `localhost:3000`,
`*.local:3000`, and the `192.168.x.x:3000` LAN range, so a browser
on laptop B can hit the supervisor UI without further config.

Open the supervisor UI from laptop A's browser to confirm it works
locally first:

* `http://localhost:3000/app/cockpit`

## Step 3 — point laptop B at laptop A

On laptop B, the only thing that changes per-demo is the API base.
Pass it on the CLI:

```bash
bash scripts/ingest_sample_dataset.py \
    --api-base http://<LAPTOP_A_IP>:8000/v1 \
    --mode live-stream \
    --sheet both \
    --rate 0.5 \
    --limit 4 \
    --insecure-skip-mtls
```

The browser on laptop B (if used) can reach the cockpit at
`http://<LAPTOP_A_IP>:3000/app/cockpit`. If a future demo flavor
needs the browser on laptop B to call FastAPI directly (bypassing
the Next.js proxy), set `NEXT_PUBLIC_API_BASE_URL=http://<LAPTOP_A_IP>:8000`
when launching `next dev`; the CORS regex already allows the
matching origin.

## Step 4 — smoke test before the audience walks in

Run this end-to-end check on a fresh stack, with laptops A and B both
ready:

```bash
# laptop B
bash scripts/ingest_sample_dataset.py \
    --api-base http://<LAPTOP_A_IP>:8000/v1 \
    --mode backfill \
    --sheet large \
    --limit 1 \
    --insecure-skip-mtls
```

Expected on laptop B:

```
[1/1] EMPRESA=Banco1 COD_REC=11082500751 → BCO-2026-NNNNNNN
accepted_with_warnings (HTTP 201; dq=…; annex=…; taxonomy normalized N)
```

Expected on laptop A's cockpit:

* A new card under Tier 1 within ~5 seconds.
* The PII in the row's narrative (`<PERSON>`, `<PE_DNI>`, free-text
  Spanish) appears redacted in the cockpit description preview.

## Known limitations

* `--insecure-skip-mtls` is sandbox-only. It forges a dev XFCC
  header so the API treats the request as mTLS-authenticated by a
  trusted reverse proxy. Real mTLS requires either uvicorn's
  `direct` mode with a TLS terminator on both laptops or a proxy
  layer that forwards the verified client cert. The production
  overlay uses real mTLS.
* The CORS allow-list is intentionally wide for the demo
  (`*.local`, `192.168.0.0/16`). Tighten the
  `SBS_API_CORS_ALLOW_ORIGINS` env var to a single literal origin
  before any production deployment.
* If laptop B can't resolve `<LAPTOP_A_IP>`, you are on a
  client-isolated network — switch to a phone hotspot.
* The cockpit SSE stream goes through the Next.js proxy at
  `/app/api/sse/*`. If you point the browser on laptop B at the
  Next.js dev server on laptop A, SSE works without further setup.
  If you point it at FastAPI directly, you must whitelist the
  origin (the default CORS regex already covers LAN ranges).
