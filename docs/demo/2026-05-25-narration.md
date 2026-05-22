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

When WS5 lands, this section grows. Jorge opens Approvals, sees the
pending row from the Findings edit, reviews Lucía's draft, approves
with edits. The decision flows into Audit within 1s.

## §Audit (WS6 — to be authored)

The audit screen shows every state-changing action — login,
switch-persona, edit-draft-narrative, send-to-approvals, approve.
The row that records Lucía's edit ("before" → "after" excerpts) is
the AI-governance closer.
