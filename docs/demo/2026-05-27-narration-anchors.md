# Demo narration anchors — May 27 walkthrough

Short list of phrases keyed to the demo path. Use these as the
verbal anchors when the visual is up. Each row is the cue, the
camera/window, and a one-sentence narration to read.

## Anchor 1 — "Real Annex 1-A data from SBS"

Window: laptop B terminal with `scripts/ingest_sample_dataset.py` mid-run.
Cue: the EMPRESA=Banco1 / EMPRESA=Banco3 line in the per-row trace.

> "This is the actual sample the SBS team shared with us — the same
> file SBS receives from institutions every month. We are not
> generating synthetic shapes; the spreadsheet on screen is what
> Annex 1-A submissions look like in production today."

## Anchor 2 — "Tier 1 NRT for high-volume, Tier 2 batch for transition institutions"

Window: laptop A cockpit, the two tier panels side by side.

> "The cards arriving on the left are Tier 1 — near-real-time
> ingestion for the high-volume banks. The cards on the right are
> Tier 2 — batch submissions from cooperatives and smaller
> financial entities. Same canonical record, same dashboard, two
> different operational pipes."

## Anchor 3 — "Taxonomy harmonized in-flight — different banks, same canonical record"

Window: laptop A findings page for a Tier 2 row.
Cue: the Findings panel showing canonical fields (`pagina_web`,
`credito_pyme`, etc.) and the `taxonomy_normalizations` audit row
in the cross-screen audit drawer.

> "Banco1 sent 'Página web de la empresa'. Banco3 sent 'PAG. WEB DE
> LA EMPRESA'. They are the same channel. The platform normalized
> both to `pagina_web` before the row hit canonical storage, and
> the audit chain carries the exact mapping, including the
> dictionary version. SBS can re-run the same query across
> institutions without per-bank handling."

## Anchor 4 — "PII redacted before canonical storage, raw kept in restricted policy"

Window: laptop A findings page narrative panel.
Cue: tokens like `<PE_DNI>`, `<PERSON>`, `<NUMBERS>` visible
inline in the narrative; the redaction policy line at the top of
the panel.

> "The DNI, the name, the contract number — none of these appear
> in the canonical complaint or anywhere on this screen as raw
> values. The raw text lives in a separate restricted store with a
> documented policy version, and the audit chain records exactly
> which entities were redacted and how. The supervisor sees what
> they need; the regulated data stays scoped."

## Optional anchor — "Unknown surface forms don't break the pipeline"

Window: laptop A cockpit, a row with the orange `taxonomy
unrecognised` flag.

> "When an institution sends a surface form we have not seen
> before, ingestion does not block. The row is accepted, the
> canonical value is preserved as-is, and the audit chain carries
> a warning so we can decide whether to grow the dictionary or
> push back on the institution. Day-one operational realism, not
> a perfect-world assumption."

## Closing line

> "Everything you have just seen runs on-prem and seeded — no
> cloud calls, no LLMs. The next prompt opens the agent layer on
> top of this canonical substrate."
