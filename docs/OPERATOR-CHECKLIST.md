# Operator checklist — go-live gate list

This repository is a **production-ready reference implementation — production
deployment requires completing this checklist.**

Every box below is something the code cannot establish about itself. The gate
suite proves the software behaves; this list is the operational, model, and
governance work that turns a verified build into a deployment that can carry
regulated traffic. Nothing here is optional, and nothing here is a code change.

How to use it: assign each section an accountable owner, work top to bottom, and
keep the evidence. A supervisory authority will ask to see the pen-test report
and the restore drill, not a tick in a markdown file.

Deployment mechanics are in [PRODUCTION.md](PRODUCTION.md); the sharp edges are
in [HANDOVER-NOTES.md](HANDOVER-NOTES.md).

---

## Deployment

**Owner:** platform engineering / infrastructure

- [ ] **Penetration test performed** against the deployed stack, findings
      triaged, and anything exploitable fixed or formally accepted. Scope must
      include the institution-facing API's mTLS + OAuth + HMAC chain and the
      cockpit's session handling.
- [ ] **Load test at target volume.** `scripts/perf-smoke.sh` in this repository
      is **sandbox-scale and indicative only — it is not a load test.** Run a
      real one at your projected peak submission rate, with your data volumes,
      against production-shaped infrastructure. Record p50/p95/p99 and error
      rate, and confirm the database connection ceiling holds at that
      concurrency (see PRODUCTION.md §4).
- [ ] **TLS certificates from a real CA**, for both the public endpoint and the
      client certificates issued to each supervised institution. The `dev-ca/`
      material in this repository is a development convenience and must not
      appear in any production trust chain.
- [ ] **Certificate lifecycle defined** — issuance, rotation, revocation, and
      expiry monitoring for institution client certs. An expired institution
      certificate is an outage for that institution.
- [ ] **Secrets manager wired.** No `.env` file anywhere in production; every
      secret injected from the manager. Confirm the inventory in
      PRODUCTION.md §2 is fully covered, including
      `SBS_API_INTERNAL_API_SECRET` matching on both sides of the hop.
- [ ] **Secret rotation rehearsed** at least once, including the per-institution
      HMAC secrets and the rotation grace window.
- [ ] **Backups configured and a restore drill completed.** Point-in-time
      restore for PostgreSQL; the audit tables (`agent_runs`,
      `validation_audit`) must be recoverable to a point in time. A backup that
      has never been restored does not count.
- [ ] **Monitoring and alerting live** — OTel traces reaching a collector,
      structured JSON logs shipping, and alerts firing on queue depth,
      ingestion stall, validator failure rate, signing failure rate, and
      readiness flapping. The repository ships no dashboards or alert rules;
      these are yours to build (PRODUCTION.md §6).
- [ ] **Internal API confirmed unreachable from the internet.** Verify by
      attempting to reach `/v1/internal/*` from outside the trust boundary.
- [ ] **Auth stub off and demo mode off** — `SBS_API_AUTH_STUB_ENABLED=false`
      on the institution-facing process, `SBS_DEMO_MODE=false` on the cockpit.
      Demo mode mints a session for all three personas without authenticating
      anyone.
- [ ] **mTLS mode set and the gateway hardened.** If running `proxy` mode, the
      gateway strips client-supplied `X-Forwarded-Client-Cert` on ingress and
      nothing can bypass the gateway to reach the API directly.
- [ ] **Keycloak in production mode** — `start`, not `start-dev`; PostgreSQL
      backing store, not `dev-file`; bootstrap admin rotated; realm managed as
      configuration rather than re-imported on every boot (PRODUCTION.md §3).
- [ ] **Cockpit replica count decided.** The session store is in-process and the
      Redis backend is **not implemented**, so the cockpit runs as a single
      replica or behind strict sticky sessions, and a restart logs everyone out.
      Either accept this limitation explicitly or implement the Redis-backed
      store before go-live (PRODUCTION.md §5).
- [ ] **Migration procedure integrated into the deployment pipeline** as a
      pre-deploy step that completes before new containers start — never from
      application startup.
- [ ] **Upgrade and rollback rehearsed** on staging against restored production
      data, per PRODUCTION.md §8. Rollback plans around the backup, not around
      `alembic downgrade`.
- [ ] **All ten gates plus the pytest suite green** against the production-shaped
      stack, including the `-full` variants with their live-stack halves.

---

## Models

**Owner:** the team accountable for the AI/ML runtime

- [ ] **On-prem path proven against live vLLM on your target hardware.**
      `SBS_API_MODEL_PROVIDER=on_prem` is the default and **has never once been
      observed working against a real vLLM endpoint** — not in this engagement,
      not on any machine used to build this repository. Every on-prem code path
      is therefore unexercised in practice. Expect integration problems no test
      in this repository could have caught, and budget for them. Prove it end to
      end before it carries traffic.

      *or*

- [ ] **Cloud legal gate formally approved.** If running
      `SBS_API_MODEL_PROVIDER=cloud` (Azure OpenAI), the approval that
      `SBS_API_CLOUD_LEGAL_APPROVED=true` asserts must be a real, recorded
      decision by the accountable authority — covering the fact that complaint
      narratives leave your infrastructure. The cloud provider has been
      exercised live **against synthetic data only**.
- [ ] **Provider posture confirmed as deliberate.** `replay` is fixture-backed
      and logs a warning on every request; it must never serve production. Check
      what is actually configured rather than what is assumed.
- [ ] **Real classifiers wired if replacing the rules table.** The shipped
      classification is deterministic and rules-based. If you substitute a
      trained model (BETO or otherwise), it needs its own evaluation,
      versioning, and drift monitoring before it informs decisions.
- [ ] **Scaffolds understood and either completed or accepted.** `rank_features`
      returns a constant `DEFAULT_FEATURES` list under `xgboost-replay-v1`;
      `reclamito`, `lupaman`, and `insight-chatbot` are registry entries with no
      runtime; the cross-source correlator returns an empty result for every
      complaint except the golden one. None of these is a bug — all are
      documented as incomplete by design in
      [HANDOVER-NOTES.md](HANDOVER-NOTES.md#known-incomplete-by-design). Confirm
      no downstream process treats their output as analysis.
- [ ] **Model output positioned as decision-informing, not decision-making**, in
      both the interface and the operating procedure.

---

## Governance

**Owner:** the supervisory authority's policy / data governance function

Written against SBS, because that is the authority this was built for. Another
authority substitutes its own equivalents — the shape of each decision holds.

- [ ] **Institution-code mapping decided.** This one flips a component from
      recording to enforcing. DIValeVale currently runs ahead of Triage, writes
      one `validation_audit` row per complaint, and **its verdict stops
      nothing** (`record_only=True`). Making it a real gate requires an
      authoritative `institution_id → institution_code` mapping: Pass 1 needs
      `institution_code` matching `^[A-Z]{3}_[A-Z]+_\d{3}$`, every surface
      issues `SBS-001234`-style ids, and no mapping exists in the code or the
      database. Until it does, the Tier-1 verdict is `INVALID` / `REJECTED` for
      every real record and is correctly ignored.

      *For another authority:* decide what your canonical institution
      identifier is and how it maps to the code the validation rules expect.

- [ ] **ADR 0026 amount/currency decision made.** ADR 0026 fixes Tier 1 at a
      15-field Anexo 1-A subset carrying neither `amount_claimed` nor
      `currency`, while Pass 1 requires an amount for the `COBRO_INDEBIDO`
      family. Enforcing today would either stop Triage on every real Tier-1
      record or fire a spurious enrichment webhook at the institution for each
      one. Someone with authority over the contract must decide whether to widen
      the subset or narrow the rule. This is the second of the two blockers on
      the item above.

      *For another authority:* reconcile the fields your intake contract
      collects with the fields your validation rules require, before switching
      validation from advisory to blocking.

- [ ] **Data-source agreements in place for cross-source correlation.** The
      correlator is built to combine complaint data with other sources.
      Correlating across sources needs a legal basis and an agreement with each
      source owner — obtained before the capability is switched on, not after.
- [ ] **AI-governance approval for decision-informing use.** A formal sign-off
      that model-assisted analysis may inform supervisory decisions, covering
      the human-in-the-loop control (the approvals workflow), the audit trail
      (`agent_runs` records which provider actually served each run), and what
      happens when the model is wrong.
- [ ] **Retention and disposal policy applied** to complaint records, batch
      files (`SBS_API_BATCH_STORAGE_PRUNE_DAYS`), and the audit tables —
      consistent with the authority's regulatory retention obligations.
- [ ] **PII redaction policy reviewed and accepted.** The redaction engine is
      deterministic and rules-based, covering DNI, RUC, Peruvian mobile numbers,
      email, account/card numbers, and an allowlist of known names. Confirm that
      set matches what your jurisdiction treats as personal data, and that the
      residual risk of a miss is accepted by the accountable owner.
- [ ] **`agent_runs` provenance gaps understood — both of them.**
      `model_provider = NULL` has two causes, and a reporting filter of
      `model_provider IS NOT NULL` drops both. (a) Rows predating migration
      `20260810_0001`, deliberately left un-backfilled rather than guessing into
      an audit table; that set cannot grow. (b) Runs on the journey /
      demo-ingestion path (`/v1/sandbox/complaints/granular`, which the
      cockpit's `/app/ingestion` loop drives), which record NULL **today**,
      including successful `triage` / `investigation` / `synthesis` rows. So on
      a database that has seen `/app/ingestion` traffic that filter excludes
      current analysis, not just history. The canonical Tier-1 and Tier-2 paths
      record provenance correctly and `stage-h-full` asserts it. Confirm which
      surfaces your deployment actually uses, and whether your reporting
      tolerates (b).

---

## Sign-off

| Section | Owner | Date | Signature |
|---|---|---|---|
| Deployment | | | |
| Models | | | |
| Governance | | | |

Production deployment is authorised when all three sections are complete and
signed.
