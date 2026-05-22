# SBS SupTech — May 25 demo narration

Authored Prompt 10 / WS4. Updates each workstream commit as panels
land. The narrator (Antoine or Oumaïma) reads from this file during
rehearsal Day 3; the live demo follows the same beats.

## §Findings deep-dive

Anchor complaint: **BCO-2026-000001** on BANCO_DEMO_001.

The cockpit's anomaly card links here. The drilldown opens with the
header — institution, source tier (Tier 1 · API), received-at,
severity high — and the customer narrative below it with anonymization
spans visibly redacted (`[REDACTED:pii_name]`).

### BERT confidence panel
"Watch the confidence: **0.87** on `undisclosed-fees-credit`. That's a
number, not a label — the system tells us how sure it is, and the
top-3 next to it shows the alternatives the model considered."

### XGBoost feature importance panel
"Now look at the feature importance. The highest positive contributor
is **`narrative_mentions_fee_undisclosed`** at **+0.27**, ahead of
`vulnerable_consumer_flag` and `prior_findings_180d`. The model
latched onto a sub-pattern in paragraph two of the narrative — a
comisión por mantenimiento not in the explicit Annex 1-A taxonomy."

### Scripted edit gap (the load-bearing demo moment)
The agent-drafted summary in the **Draft narrative** panel reads:

> Disputa de cliente sobre comisiones de cuenta.

That's deliberately incomplete. Lucía clicks **Edit draft**, types in
the missing mention, and saves:

> Disputa de cliente sobre comisiones de cuenta, incluida una comisión
> por mantenimiento no informada referida en el párrafo dos de la
> narrativa.

The save writes:
- a new `complaint_narrative_drafts` row (before/after preserved);
- one `audit_events` row, `action='edit-draft-narrative'`,
  `actor_id=lucia@sbs.gob.pe`, `diff={before_excerpt, after_excerpt}`.

The audit row is what makes the WS5 Approvals view trustworthy later
— Jorge sees exactly what Lucía changed.

### Agent reasoning panel
"Three runs on this complaint. The classifier shows green across
anonymizer → BERT → XGBoost. The narrative-drafter ran clean. The
cross-source-correlator returned composite_score 0.74 with the four
channel contributions you saw on the cockpit. Every step has its tool
version, its elapsed time, and its status."

The audience can also drill into other complaints to see the agent
governance story — **BCO-2026-000002** has two partial runs (BERT
timeout + XGBoost unavailable) and **BCO-2026-000003** has a failed
run (anonymizer error). The reasoning panel renders each distinctly:
medium pill for partial, critical pill for failed. The system is
honest about when it didn't work.

### Send to Approvals
After the edit lands, Lucía clicks **Send to Approvals**. A pending
row appears in WS5's queue; an audit row records the handoff. The
button changes to a pill: "Already in approvals queue #N". A second
click is idempotent — no duplicate row.

## §Cockpit opening (already written, WS3)

(See WS3 commit notes — the cockpit opens with KPIs + Tier 1/Tier 2
side-by-side + anomaly card. The 90-second beat is unchanged.)

## §Approvals moment (WS5 — to be authored)

Antoine switches persona to **Jorge** via the top-bar switcher. The
nav rail's role indicator flips from Analista to Jefe; the URL stays
on Findings; Antoine clicks Approvals in the nav rail. The audit row
recording the persona switch lands silently in `audit_events`
(`actor_id=antoine`, `meta.from_persona=lucia`, `to_persona=jorge`).

The queue shows one pending item — the one Lucía sent up. KPIs at the
top: pending 1, approved today 0, rejected today 0, median T2D —.
Click the row. Detail opens.

Pinned evidence shows three columns:
- **Taxonomy hits**: `ANX1A-FEE-MAINT-001` matching "comisión por
  mantenimiento" in paragraph two.
- **Top features**: `narrative_mentions_fee_undisclosed` +0.27,
  `vulnerable_consumer_flag` +0.19, `prior_findings_180d` +0.16.
- **Channel contributions**: indecopi +0.30, social +0.20,
  complaints +0.18.

Below it, the same panels Lucía saw — Narrative + Classification +
Feature importance + Agent reasoning — render exactly as before.
Decision-history is empty (this is the first time Jorge has opened
this approval).

Jorge clicks **Approve with edits**. The Edit modal opens with the
narrative pre-filled to Lucía's saved draft (which now includes the
maintenance-fee mention). Jorge adjusts the closing sentence to add
"institutional notification recommended within 5 business days." and
fills the rationale: *"Edit clarifies the recommended remediation
window for institutional response."* (82 chars; well above the 20-
char minimum the modal's helper text shows until threshold.)

Save. The modal closes. The decision row flips to "Approved ·
approve-with-edits". Behind the scenes the four-write effect lands:

- `supervisory_observations` gets a row with Jorge's edited narrative.
- `agent_feedback` gets a row with `decision='approve-with-edits'`
  and `edit_diff={before, after}` for the AI-eval pipeline.
- `pending_approvals.status` flips from 'pending' to 'approved' with
  the decision_action, decided_by, decided_at, decision_rationale.
- One `audit_events` row lands with action='approve-with-edits-
  finding' and the nine-key meta the decision-audit contract test
  pins (pending_approval_id, complaint_id, agent_run_id,
  decision_action, observation_id, feedback_id, severity,
  rationale_excerpt, edit_diff).

If the narration drifts from the code in a future revision, fix one
or the other in the same PR — they are the contract.

## §Audit (WS6 — to be authored)

The audit screen shows every state-changing action — login,
switch-persona, edit-draft-narrative, send-to-approvals, approve.
The row that records Lucía's edit ("before" → "after" excerpts) is
the AI-governance closer.
