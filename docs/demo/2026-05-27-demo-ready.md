# P11 demo-ready — walkthrough

Date: 2026-05-27
Tag: `p11-demo-ready`
Branch: `part-09/api-pii-agent-foundation`

## Summary

The sandbox can now ingest the real Annex 1-A sample the SBS team
shared (`data/sbs_sample/SAMPLE_MUESTRA_ENTITY_CLAIMS.xlsx`, 200 rows
across two sheets) end-to-end. Each row goes through:

```
received → auth → schema validated → taxonomy normalized →
PII redacted → canonical persisted → DQ + Annex 1-A checks →
audit chain (6 rows) → cockpit SSE delta
```

The two sheets carry the same logical taxonomy under deliberately
different surface forms (`"Página web de la empresa"` vs `"PAG. WEB
DE LA EMPRESA"`). The new in-flight normalization step maps both to
`pagina_web`. Surface forms the dictionary doesn't recognise pass
through with `flag_unknown_taxonomy=true` rather than blocking
ingestion, and emit a `taxonomy-unknown-term` audit warning.

## What landed

* `api/sbs_api/taxonomy/dictionary_v1.py` — hardcoded dictionary v1
  for `canal`, `producto`, `motivo`, `estado_reclamo`,
  `tipo_resolucion`. Case-insensitive, accent-stripped,
  whitespace-collapsed lookup; 8 field paths share four canonical
  maps.
* `api/migrations/versions/20260526_0001_p11_demo_ready_columns.py` —
  additive migration adding five nullable columns to `complaints`
  (`fecha_resolucion`, `tipo_resolucion`, `descripcion_resolucion`,
  `estado_reclamo`, `monto_pendiente`) and `raw_descripcion_resolucion`
  to `raw_complaints`. Reversible; existing rows backfill to NULL.
* `api/sbs_api/demo_ingestion/orchestrator.py` — taxonomy step
  inserted between schema validation and redaction; audit chain
  grows from 5 to 6 rows (renamed `demo-complaint-received` →
  `complaint-received` and added `taxonomy-normalized`); `agent_run.final_output`
  gains `taxonomy_normalizations[]` + `flag_unknown_taxonomy`; the
  cockpit SSE delta exposes `flag_unknown_taxonomy`.
* `scripts/ingest_sample_dataset.py` — drives the sandbox endpoint
  off the xlsx. `--mode backfill` for as-fast-as-possible loading,
  `--mode live-stream --rate 0.5` for visible cockpit pacing; per-row
  trace masks PII before stdout. Reuses the existing
  `institution_push_demo.py` auth chain helpers (OAuth + HMAC +
  Idempotency-Key + dev XFCC).
* CORS middleware wired in `api/sbs_api/app.py`, controlled by
  `SBS_API_CORS_ALLOW_ORIGINS`. Default opens `localhost:3000`,
  `*.local:3000`, and `192.168.0.0/16:3000` for the two-laptop demo.
* Next.js dev server binds `0.0.0.0:3000` (`app/package.json`).
* Findings UI surfaces the five new columns (Estado, Tipo de
  resolución, Fecha, Monto pendiente, plus a Descripción de la
  resolución card with the redacted text).

## Column mapping (xlsx → canonical)

| xlsx column   | Canonical column / treatment                                   |
|---------------|----------------------------------------------------------------|
| COD_REC       | `institution_complaint_id` (request only; not persisted)       |
| TID_CLI       | `raw_complaints.raw_payload.tid_cli`                           |
| NRO_CLI       | `raw_complaints.raw_payload.nro_cli` (PII — restricted store)  |
| NCL_CLI       | `raw_complaints.raw_payload.ncl_cli` (PII — restricted store)  |
| COD_CLI       | `raw_complaints.raw_payload.cod_cli`                           |
| FEC_ING       | `complaints.received_date`                                     |
| CNL_ING       | `complaints.channel` (normalized via canal map)                |
| CNL_OPE       | `complaints.submission_method` (normalized)                    |
| FEC_AMP       | request-only (DQ rule input)                                   |
| CNL_AMP       | request-only (DQ rule input)                                   |
| FEC_RES       | `complaints.fecha_resolucion`                                  |
| CNL_PAC       | request-only; taxonomy-normalized for audit                    |
| UBI_REC       | request-only (DQ rule input)                                   |
| PRD_SBS       | `complaints.product_category` (normalized via producto map)    |
| MOT_SBS       | `complaints.motivo_code` (normalized via motivo map)           |
| SUB_SBS       | request-only                                                   |
| DET_REC       | redacted → `complaints.description_text`                        |
| TIP_RES       | `complaints.tipo_resolucion` (normalized)                      |
| DET_RES       | redacted → `complaints.descripcion_resolucion`                  |
| PRD_EMP       | request-only                                                   |
| EST_REC       | `complaints.estado_reclamo` (normalized)                       |
| COD_PRV       | `complaints.original_reference_id` (when present)              |
| BAN_SEG       | DQ rule input                                                  |
| PRD_SBS_SEG   | DQ rule input (conditional on BAN_SEG=SI)                      |
| MOT_SBS_SEG   | DQ rule input                                                  |
| SUB_SBS_SEG   | DQ rule input                                                  |
| MNT_PEN_REC   | `complaints.monto_pendiente` (decimal cast)                    |
| EMPRESA       | profile selector (Banco1/2 → SBS-001234, Banco3/4 → SBS-005678)|

## Taxonomy dictionary v1 (committed)

* **CANAL** — `pagina_web`, `telefono`, `oficina_o_domicilio`,
  `correo_electronico`, `app_movil`, `cajero`, `billetera_digital`,
  `plataforma_digital`, `no_aplica`, `whatsapp`.
* **PRODUCTO** — `credito_consumo`, `credito_pyme`,
  `tarjeta_credito`, `cuenta_ahorros`, `cuenta_corriente`,
  `transferencia`, `servicios_varios`, `credito_hipotecario`,
  `deposito_plazo`.
* **MOTIVO** — `operaciones_no_reconocidas`,
  `transacciones_no_procesadas`, `cobros_indebidos`,
  `informacion_insuficiente`, `problemas_cajeros`,
  `error_datos_usuario`, `incumplimiento_clausulas`,
  `disconformidad_no_atencion`.
* **ESTADO_RECLAMO** — `atendido`, `en_proceso`, `pendiente`.
* **TIPO_RESOLUCION** — `favor_usuario`, `favor_entidad` (FI-named
  variants like "A favor de Caja Arequipa" fold into
  `favor_entidad`).

Each normalization writes one `taxonomy-normalized` audit row with a
diff carrying `{field_path, original_value, canonical_value,
dictionary_version: "taxonomy-v1"}`. Each unknown writes one
`taxonomy-unknown-term` audit warning with the same shape minus
`canonical_value`.

## Two-laptop demo setup

See [2026-05-27-two-laptop-setup.md](2026-05-27-two-laptop-setup.md)
for the operator steps. Short version:

1. `bash scripts/dev-up.sh` on laptop A.
2. `SBS_API_MTLS_MODE=proxy bash scripts/run-api.sh` (laptop A,
   binds 0.0.0.0:8000).
3. `cd app && npm run dev` (laptop A, binds 0.0.0.0:3000).
4. `ipconfig getifaddr en0` on laptop A → `<LAPTOP_A_IP>`.
5. On laptop B:
   ```
   bash scripts/ingest_sample_dataset.py \
       --api-base http://<LAPTOP_A_IP>:8000/v1 \
       --mode live-stream --sheet both --rate 0.5 \
       --limit 4 --insecure-skip-mtls
   ```
6. Laptop A's cockpit shows new cards within ~5 s.

## Known limitations

* **Unknown-taxonomy handling** — unknown surface forms preserve the
  raw value at the canonical column *only when it fits the column's
  varchar length* (channel/product/motive/submission_method are
  varchar(32)). Longer free-text values fall back to the column
  default; the full raw value stays in `raw_complaints.raw_payload`,
  in the `taxonomy-unknown-term` audit row, and in
  `agent_run.final_output.taxonomy_normalizations` so nothing is
  lost. The supervisor UI lights `flag_unknown_taxonomy=true` so
  rows that fell back are visible.
* **Partial pre-anonymization** — the real sample arrives with
  `<PERSON>`, `<PE_DNI>`, `<NUMBERS>` placeholders. The deterministic
  redactor leaves these placeholders alone and continues to redact
  any residual real PII in the surrounding free-text Spanish (DNI,
  email, phone, account, name allowlist).
* **CORS for production** — the default CORS allow-list is
  intentionally wide (`*.local`, `192.168.0.0/16`) for the demo.
  Tighten `SBS_API_CORS_ALLOW_ORIGINS` to a single literal origin
  before any production deployment.
* **Agent runtime** — out of scope for this prompt. The next
  prompt wires the agent loop on top of the taxonomy + DQ + audit
  substrate this prompt landed.

## Exit-gate evidence

| Gate | Result |
|------|--------|
| 1. `pytest` full suite | 642 passed, 6 skipped, 0 failed |
| 2. `npm run typecheck` + `npm run build` | clean |
| 3. `bash scripts/demo.sh --scale small` | `demo.sh: PASS` |
| 4. backfill --sheet large --limit 5 | 5/5 rows ingested; audit chain incl. taxonomy-normalized |
| 5. backfill --sheet small --limit 5 | 5/5 rows ingested; ALL-CAPS surface forms → canonical codes |
| 6. live-stream --sheet both --rate 0.5 --limit 2 | 4 rows over 8 s |
| 7. CRÉDITO DE CONSUMO → `credito_consumo` + audit row | verified in `audit_events.diff` |
| 8. UNKNOWN PRODUCT XYZ → preserved + `flag_unknown_taxonomy=true` + warning audit | verified in `complaints.product_category` and `audit_events` |
| 9. BCO-2026-000001 composite_score=0.74 invariant | `tests/test_cockpit_endpoint.py` 4/4 pass |
| 10. 5 new canonical columns surfaced in Findings panel | API + UI wired; `tests/integration/test_findings_endpoints.py` 7/7 pass |
| 11. SSE cockpit within ~5 s | publish happens synchronously after canonical persist |
| 12. No raw PII in canonical / UI / audit | `tests/integration/test_no_raw_pii_egress.py` 2/2 pass |
