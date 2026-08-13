# Data provenance

All complaint records in this repository are synthetic. No SBS production data, no real consumer complaints, and no personally identifiable information are included.

## How the data is produced

- **Generator:** `scripts/generate-synthetic-corpus.py`, seeded and deterministic — the same seed reproduces the same corpus byte-for-byte.
- **Templates:** `data/synthetic-corpus-templates.yaml` defines the narrative and field templates the generator draws from.
- **Committed golden sample:** `data/synthetic-corpus-golden/` holds 200 rows for each of three fictional demo institutions, each with a manifest recording row counts, reporting period, schema version, and a SHA-256 checksum of the CSV. Regenerate with `make corpus-golden`.
- **Full corpus:** `make corpus` regenerates the ~10k-row corpus locally; it is gitignored and never committed.
- **Fidelity tiers:** ADR 0036 documents how synthetic records approximate the statistical shape of the Annex 1-A schema — the curated 15-field subset the API implements, per [ADR 0026](adr/0026-anexo-1a-curated-subset.md) — without deriving from real submissions.

## Fictional identities

Demo institutions use placeholder registration codes. Demo personas and login accounts use role names ("Conduct Supervisor (Demo)") and addresses under `sandbox.example.com`, a domain reserved by RFC 2606 for documentation and testing, making their fictional nature unambiguous.

## Bundling rationale

The synthetic golden sample is committed deliberately so the sandbox runs end-to-end on a fresh clone with no external data dependency.
