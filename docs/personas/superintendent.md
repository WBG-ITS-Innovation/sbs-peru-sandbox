# Superintendent persona

Plain-language note for the SBS Superintendent role in the SupTech cockpit.

## What the Superintendent sees

Executive aggregates only. The Superintendent view **never** shows
per-complaint rows or raw complaint narrative. It surfaces:

- Cohort health (one GREEN/AMBER/RED band per cohort, with a one-sentence why)
- Top 5 patterns this week, each with a plain-language Spanish summary
- FIBrief activity counts (sent / acked / overdue) — counts, not contents
- Sector broadcasts awaiting co-approval

Server-side enforcement: every endpoint the Superintendent token reaches
runs a data-shape sentinel that rejects any per-complaint identifier or
raw narrative before the response leaves the server.

## The one exception: sector-broadcast co-approval

The Superintendent is **read-only across the platform, with a single
deliberate exception**: they may co-approve a *sector broadcast* as the
**secondary** approver.

Why this is a feature, not a contradiction:

- A sector broadcast is a **sector-level policy action** — SBS warning
  every peer institution in a cohort that a fraud campaign is emerging.
  Misuse damages SBS's relationship with the whole sector at once.
- Broadcasts therefore require **dual approval**: a primary approver
  (Conduct Supervisor or Unit Head) and a distinct secondary approver
  (Unit Head **or** Superintendent), each with a 50-character rationale.
- Letting the Superintendent co-approve puts the sector-level decision
  at the right level of seniority without granting any per-complaint
  visibility. The Superintendent still never sees an individual
  complaint or a raw narrative — they approve the *shape* of the threat
  and the recipient list.

Scope: `sector_broadcast:approve_secondary` (granted to `sbs:conduct:head`
and `sbs:superintendent`). All other Superintendent scopes are read-only.
