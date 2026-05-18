# ADR 0026 — Anexo 1-A curated subset for the May 25 sandbox

- **Status:** Accepted
- **Date:** 2026-05-18
- **Target prompt / Part:** Prompt 5 / Part 2
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer in consultation with the WBG SBS engagement.

## Context

Resolución SBS N° 04036-2022 — Anexo N° 1-A — enumerates 23 fields that
supervised institutions must record for each complaint, plus additional
fields for specific institution types. Implementing the full 23-field
taxonomy (including the four PII-bearing fields and the code lists in
Anexos A through D) inside the nine-day May 25 sprint is not feasible, and
the May 25 audience does not need full taxonomy coverage. They need to see
the *integration shape* — what an institution will integrate against — not
every Anexo 1-A field.

The May 25 demonstration also has a deliberate PII-minimisation posture:
the sandbox runs on synthetic data, and the institution-facing API contract
is shaped around pseudonymous identifiers (`complaint_id`, `institution_id`,
`original_reference_id`) rather than personally-identifying data
(`Número de documento de identidad`, `Nombre completo del cliente`,
`Código de cliente`). The full-PII version of the contract is a policy
decision belonging to SBS, not a default that should be coded into the
sandbox.

## Decision

The May 25 sandbox implements a curated 15-field subset of Anexo 1-A. The
subset covers identification, classification, severity, narrative,
complainant geography, and resolution status. The full Anexo 1-A taxonomy
arrives in a later release alongside the Standards Pack v1.0.0 distribution
(see PLAN.md Part 11). When the spec and the Pydantic models disagree on a
field's shape, the OpenAPI specification wins (ADR 0027).

### The 15-field subset

| Field (API)                | Type (API)         | Anexo 1-A counterpart | Source section |
| -------------------------- | ------------------ | --------------------- | -------------- |
| `complaint_id`             | string, pattern    | #1 Código del reclamo | Resolución Anexo 1-A |
| `institution_id`           | string, pattern    | Empresa código (Reportes RR1 §2) | Resolución Reportes section |
| `received_date`            | ISO date           | #6 Fecha de ingreso   | Resolución Anexo 1-A |
| `complainant_doc_type`     | enum (5 codes)     | #2 Tipo de documento de identidad | Resolución Anexo 1-A, Anexo A |
| `product_category`         | enum (8 codes)     | #14 Operación/Servicio/Producto SBS | Resolución Anexo 1-A, Anexo B |
| `channel`                  | enum (7 codes)     | #7 Canal de ingreso   | Resolución Anexo 1-A, Anexo A |
| `motivo_code`              | enum (8 codes)     | #15 Motivo del reclamo SBS | Resolución Anexo 1-A, Anexo C |
| `severity`                 | enum (4 levels)    | **No counterpart.** Prototype divergence. | Internal supervisory triage |
| `description_text`         | string, 10–8000 ch | #17 Detalle completo de reclamo | Resolución Anexo 1-A |
| `description_language`     | enum (es/qu/ay/en) | **No counterpart.** Prototype divergence. | Locale handling |
| `complainant_age_range`    | enum (7 buckets)   | **No counterpart.** Prototype divergence (in lieu of PII fields). | PII-minimisation |
| `complainant_district`     | string, INEI ubigeo | #13 Ubicación geográfica | Resolución Anexo 1-A |
| `submission_method`        | enum (7 codes)     | #8 Canal de operación | Resolución Anexo 1-A, Anexo A |
| `original_reference_id`    | string or null     | #23 Reclamo previo    | Resolución Anexo 1-A |
| `resolution_status`        | enum (pendiente/atendido/anulado) | #22 Estado | Resolución Anexo 1-A, exact wording |

### Anexo 1-A fields deliberately excluded

The following Anexo 1-A fields are **excluded** from the May 25 sandbox.
This is a sandbox-design decision, not a permanent omission. The
extensibility of the design supports their addition in Part 11.

- #3 Número de documento de identidad — PII. Excluded.
- #4 Nombre completo del cliente — PII. Excluded.
- #5 Código de cliente — PII (institution-internal). Excluded.
- #9 Fecha de comunicación de ampliación — secondary lifecycle field. Deferred.
- #10 Canal de comunicación de ampliación — secondary lifecycle field. Deferred.
- #11 Fecha de resolución — derived from PATCH /status timestamp; deferred.
- #12 Canal de respuesta — secondary lifecycle field. Deferred.
- #16 Sub-motivo de reclamo SBS — extends #15; deferred.
- #18 Resolución del reclamo (a favor del usuario / de la empresa) — derived from PATCH /status reason; deferred.
- #19 Respuesta al reclamo — secondary lifecycle field. Deferred.
- #20 Monto reclamado — financial amount; deferred until currency-handling ADR lands.
- #21 Nombre comercial del producto o servicio — deferred to Part 11.

### Prototype divergences without Anexo 1-A counterparts

Three fields in the subset have no counterpart in the resolución. They are
documented here so the divergence is explicit:

- `severity` — used by the Part 5+ supervisory agents for triage. Whether
  severity belongs on the institution-submitted payload, or on a separate
  supervisor-internal model, is a policy question flagged for the May 25
  review (see `docs/sessions/2026-05-18-prompt-05-open-questions.md` §1.3).
- `description_language` — included to handle Quechua / Aymara / English
  narratives. The resolución is silent on language tagging. Low risk; the
  field is informational.
- `complainant_age_range` — bucketed proxy for demographics that avoids
  storing raw date-of-birth or document number. Included in lieu of the
  resolución's PII fields. Flagged for SBS review (open-questions §1.3).

### Code-list subsets

Each of the four enum fields backed by an Anexo A / B / C code list
(`complainant_doc_type`, `product_category`, `channel`, `submission_method`,
`motivo_code`) carries a **representative subset** of the resolución's
codes. The May 25 sandbox subset is documented in the OpenAPI specification
and the Pydantic enum. The full code-list distribution (canonical CSV +
JSON, with deprecation policy) is deferred to Part 11 per PLAN.md.

## Precedent

This is a *minimum viable schema* decision. The pattern of publishing a
minimum viable schema alongside a larger full schema is well-established
in regulator-domain practice. Cite from
[docs/research/market-comparators.md §2.1](../research/market-comparators.md#21-us-cfpb-consumer-complaint-database):
the CFPB publishes a tightly curated set of fields (product, sub-product,
issue, sub-issue, narrative, company, state, ZIP, tags, submission channel,
company-response timing, complaint ID) and treats narrative governance as
a separate consent-gated track. The CFPB pattern shows that a regulator
can ship a complete-feeling complaint surface with a curated, not
exhaustive, field set; supplementary data (the original narrative;
demographic fields) is layered behind separate policy gates.

Cite also
[docs/research/market-comparators.md §2.3](../research/market-comparators.md#23-uk-fca-complaints-reporting-regime):
the FCA's PS25/19 (2025–2026 modernization) introduces "permission-based
reporting" — institutions submit the sections relevant to their regulated
activities and reporting regime, not every field for every firm. The May 25
sandbox subset follows the same logic: a minimum viable submission set that
SBS can grow into the full Anexo 1-A taxonomy via additive changes to the
spec.

Cite also
[docs/research/market-comparators.md §4](../research/market-comparators.md#4-two-tier-regulatory-data-collection-precedents):
ECB's BIRD reporting dictionary explicitly recommends "proportionality —
limiting reporting obligations for small banks to preserve proportionality."
The May 25 curated subset is the smallest viable surface that demonstrates
institutional integration; it is a proportionality choice in the same
spirit, scaled to the sprint timeline rather than to bank size.

## Divergence

This decision diverges from "implement the full Anexo 1-A on day one." That
stance is rejected because (a) it is not achievable in nine calendar days
for a solo developer; (b) the May 25 audience reads the integration shape
and the resolución reconciliation, not the field count; and (c) shipping
a PII-bearing payload contract in a sandbox before SBS has signed off on
the PII envelope creates policy risk the prototype should not carry.

This decision also diverges from "use the full code lists from Anexo A
through D inline in the spec." That is rejected because the full code
lists are the deliverable of Part 11 (Standards Pack distribution), not of
Part 2. Inlining a partial code list now and then breaking it apart in
Part 11 would be churn.

## Consequences

- Institutions integrating against the May 25 sandbox will operate against
  the curated 15-field subset and be told plainly that the full Anexo 1-A
  arrives in a later release. The developer-portal description sets this
  expectation.
- The three prototype-divergence fields (`severity`, `description_language`,
  `complainant_age_range`) are flagged for the SBS review. The maintainer
  reads `docs/sessions/2026-05-18-prompt-05-open-questions.md` at the
  closeout typed approval gate and decides whether to remove, retain, or
  defer each.
- The four PII-bearing Anexo 1-A fields (#3, #4, #5 — and arguably the
  user-narrative #17 if it is treated as PII under SBS data-protection
  rules) require an SBS policy decision before any institution integrates
  against a non-sandbox version of this contract. Tracked in the
  open-questions file.
- The code-list subsets in the enums are representative, not canonical.
  The OpenAPI `description` for each enum cross-references this ADR and
  PLAN.md Part 11 so institutions reading the spec understand the
  provisional status.
- `tests/test_anexo_1a_taxonomy.py` carries one test per constraint with
  the docstring naming the resolución section that produced it. When the
  subset grows in a future release, those tests grow with it; the docstring
  references stay readable.

If the resolución reconciliation surfaces an error in the mapping — a
field-name choice that doesn't match the Spanish wording, a code-list
subset that misrepresents the canonical set — the correction lands in
this ADR (via an amendment, not a silent edit) and in the OpenAPI spec
+ Pydantic models in the same PR.
