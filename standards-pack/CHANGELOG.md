# SBS Complaints Standards Pack — CHANGELOG

Hand-authored (like `recipes/`). The pack version is set by
`scripts/build-standards-pack.sh` (`PACK_VERSION`) and recorded in the
generated `manifest.json`.

## 0.2.0 — 2026-05-28

Added:
- `SupervisoryMetadata` block on `ComplaintListItem` (response-side only):
  `system_signal`, `system_signal_reasons`, `validation_verdict`,
  `triage_classified_at`.

No breaking changes to the FI submission contract. The frozen OpenAPI in
this pack is `openapi/sbs-complaints-v0.2.yaml`.

## 0.1.0 — 2026-05-18

Initial sandbox release: OpenAPI 3.1 contract, JSON Schemas, error
catalog, Python/TypeScript webhook helpers, verification recipes.
