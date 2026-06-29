# Data provenance

All complaint data in this repository is **synthetic**. It was generated for
the sandbox, and the SBS never shared real complaint data with the project
team. Nothing in this repository is, or is derived from, a real consumer
complaint or a real person.

## How the synthetic data is produced

The corpus is generated deterministically by
[`scripts/generate-synthetic-corpus.py`](scripts/generate-synthetic-corpus.py)
from a fixed seed, following the fidelity tiers described in
[ADR 0036](docs/adr/0036-synthetic-corpus-fidelity-tiers.md). The same seed
produces the same rows on any machine. Institution identifiers
(`BANCO_DEMO_001`, `COOPAC_DEMO_002`, `FINANCIERA_DEMO_003`) and the demo user
personas are invented archetypes, not real institutions or individuals.

## PII-bearing fields are deliberately not modeled

The Anexo 1-A complaint schema includes PII-bearing fields such as the
complainant's national identity document number (DNI) and full name. These
fields are **deliberately not modeled** in this project. In their place an
age-range bucket is used (for example, `25-34`) so that supervisory analytics
can run without handling personal data. The reasoning is recorded in
[ADR 0026](docs/adr/0026-anexo-1a-curated-subset.md).

## Names that appear in the data

Person-like names that appear inside synthetic complaint narratives and
fixtures (for example in `app/src/lib/journey-emails.json`) are randomly
assembled from common name parts by the synthetic-data generators. They do
not correspond to real people.

## Demo credentials

Credentials in `docker-compose.yaml` and the seed scripts are sandbox-only
defaults (for example, the Postgres and Keycloak admin logins). They exist so
the local stack starts with one command. They are not secrets and must not be
reused outside a local sandbox. Production secrets come from Helm values, not
from this repository.
