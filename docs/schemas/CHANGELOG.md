# Schema / contract changelog

Versions track `api/openapi/sbs-api-v1.yaml` `info.version`, which is the
standards-pack version institutions align to. Semantic versioning: a
minor bump is additive and backwards-compatible for FI submitters.

## 0.2.0 — 2026-05-28

Added:
- `SupervisoryMetadata` block on `ComplaintListItem` (response-side only)
  with `system_signal`, `system_signal_reasons`, `validation_verdict`,
  and `triage_classified_at`. Populated by the Triage agent, never by the
  FI. Gives `system_signal` a clean home on the list view.

No breaking changes to the FI submission contract: the `Complaint`
submission schema keeps `additionalProperties: false` and its locked
Annex 1-A field set. `SupervisoryMetadata` is excluded from FI submission
validation.

## 0.1.0 — 2026-05-18

Initial sandbox contract. Annex 1-A complaint submission (Tier 1 + Tier 2
batch), RFC 9457 problem+json error envelope, batch lifecycle, and
institution status surfaces. See ADR 0026, ADR 0027.
