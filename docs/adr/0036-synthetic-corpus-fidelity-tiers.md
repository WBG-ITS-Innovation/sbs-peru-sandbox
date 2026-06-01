# ADR 0036 — Synthetic data corpus fidelity tiers

- **Status:** Accepted
- **Date:** 2026-05-20
- **Target prompt / Part:** Prompt 8 / Part 4
- **Supersedes:** —
- **Superseded by:** —
- **Deciders:** Maintainer.

## Context

The May 25 demo and the Prompt 11 ML work both need a body of
synthetic complaint data. The demo needs it because an empty database
does not exercise the dashboards. The ML work needs it because BETO
fine-tuning and pattern detection need labelled examples.

No public corpus exists with the exact shape SBS needs: Peruvian
Spanish narratives, Anexo 1-A field structure, monetary amounts in
PEN at realistic Peruvian banking ranges, district codes from the
Peruvian INEI list. The corpus has to be generated.

Three things vary across uses:

- **Demo credibility.** Narratives need to look like real complaints
  to the SBS Conduct department head and the Superintendent, not "Lorem ipsum about banking".
- **Validation coverage.** Every row must be Anexo 1-A
  structurally valid so the ingestion pipeline accepts it.
- **Statistical realism for ML.** The Prompt 11 pattern detection
  agents will look for things like "200 complaints about one
  mortgage product over 10 days" — a uniform distribution gives
  them nothing to find.

These three are not the same axis. A corpus can be demo-credible
(realistic narratives) without being statistically realistic
(uniform distribution across institutions). The fidelity needed for
Prompt 8 is not the fidelity needed for Prompt 11.

## Decision

Three fidelity tiers, defined as a cumulative ladder.

**Tier 1: structurally valid only.** Every row passes Anexo 1-A
Pydantic validation. Narratives are placeholder text. Monetary
amounts are uniform random within a wide range. No domain
authenticity required.

**Tier 2: Tier 1 plus domain authenticity.** Peruvian Spanish
narratives generated from ~50 templates with parameter substitution
(not LLM-generated, for build determinism and audit-friendliness).
Realistic monetary amounts (log-normal distribution over the actual
Peruvian banking range). Format-valid synthetic phone numbers
(`9XXXXXXXX` Peru mobile pattern) and document IDs (DNI: 8-digit,
RUC: 11-digit with valid Modulo-11 checksum). Random distribution
over a 90-day window ending today.

**Tier 3: Tier 2 plus statistically-realistic distributions for
pattern detection.** Heavy-tail complaint frequency per institution
(Pareto-shaped, 80% of complaints concentrated in 20% of
institutions). Weekly seasonality with Friday peak (consumer-
banking complaint pattern; matched against the SBS Conduct department head's conduct-
supervision view). Correlated complaint clusters following synthetic
operational incidents — e.g., 200 complaints about a single mortgage
product over 10 days, simulating an institution-level conduct
failure. Prudential-versus-conduct pattern distinction: prudential
patterns concentrate by counterparty / exposure (sparse but high-
impact, matching the SBS Conduct department head's prudential lens), conduct patterns
spread across many consumers (dense but lower per-incident impact).

**Prompt 8 ships Tier 2.** Tier 3 hooks via the
`--distribution-profile` flag are stubbed for Prompt 11. The flag
defaults to `uniform`; the `pattern-cluster` profile raises
`NotImplementedError` with a "lands in Prompt 11" message that
references this ADR.

**Determinism.** The generator takes a `--seed` flag (default
`2026`). Templates are stored in
`data/synthetic-corpus-templates.yaml` (committed). Templates plus
seed plus generator code give bit-identical regeneration of any past
corpus.

**Corpus storage: golden sample committed, full corpus regenerable.**
A 200-row-per-institution golden sample (~600 KB total) is
committed to `data/synthetic-corpus-golden/` for fast-test fixtures
and PR-visible record of what the generator produces. The full ~10k
corpus is **not** committed; it regenerates from `make corpus` with
the deterministic seed. `data/synthetic-corpus/` is gitignored. This
avoids 10 MB of generated-artifact bloat in git history while
preserving reproducibility (the script is deterministic) and
reviewability (the golden sample shows the data shape).

## Precedent

[docs/research/market-comparators.md §2.1](../research/market-comparators.md#21-us-cfpb-consumer-complaint-database)
is extended in this prompt for synthetic-corpus generation,
including a Tier-3-patterns subsection enumerating the four pattern
types above.

The CFPB Consumer Complaint Database is the regulator-domain
precedent for what "demo-credible synthetic complaint data" looks
like. CFPB publishes anonymised real complaints with realistic
narratives and structurally-valid metadata. Their data-fidelity
choices — preserving narrative realism, preserving distribution
shape, anonymising PII — are the load-bearing pattern. SBS cannot
publish real complaints (none have been collected yet under the new
regime), so SBS generates synthetic data that follows the same
fidelity targets: realistic narratives, realistic distribution
shape, format-valid synthetic identifiers.

The template-based (not LLM-generated) approach has separate
precedent in regulator audit practice. Generated text needs to be
inspectable in PR review: a contributor adding inappropriate content
to the template file shows up in a diff of
`data/synthetic-corpus-templates.yaml`. An LLM-generated corpus is
an opaque blob that a reviewer cannot audit row-by-row.

The deterministic-seed pattern follows the OpenSSF reproducible-
builds principle applied to data: same inputs (seed + templates +
generator code) yield the same outputs (corpus). The maintainer or
WBG reviewer can regenerate the exact corpus used in any prior demo,
given the seed.

## Divergence

We diverge from "use LLM-generated narratives for maximum realism".
LLM-generated text is non-deterministic (model version changes,
sampling temperature, prompt drift) and opaque to PR review. The
template-based approach is less varied per-row but auditable,
reproducible, and free.

We diverge from "commit the full corpus so contributors don't have
to generate it". 10 MB of generated CSV in git history is
noise-pollution that swamps real code diffs in `git log -p`. The
golden sample is small enough to commit; the full corpus is one
`make corpus` away.

We diverge from "Tier 3 by default in Prompt 8". The Prompt 8 demo
does not need clusters — it needs a credible corpus. Tier 3 is
deferred to Prompt 11 where the pattern detection agents will
actually consume it. Shipping Tier 3 stubs early lets Prompt 11
focus on the agents, not on regenerating the corpus.

We diverge from "use real anonymised complaints from another
regulator" (e.g., CFPB). Cross-regulator data carries different
field semantics (US product taxonomy, US Spanish dialect, US
monetary scale) and would need substantial transformation. Generating
Peruvian-Spanish Tier 2 directly is less work than adapting CFPB's
US-English corpus.

## Consequences

- Templates are an audit surface. A contributor adding inappropriate
  content to `data/synthetic-corpus-templates.yaml` is detectable in
  PR review.
- Tier 3 is a Prompt 11 augmentation. Agents in Prompt 12 will rely
  on Tier 3 patterns being injectable — Prompt 11 must land the
  Tier 3 generator before Prompt 12 can demonstrate non-trivial agent
  behaviour against the corpus.
- The deterministic seed plus committed templates plus the
  `make corpus` target give any contributor (or any reviewer at WBG
  or SBS) the ability to regenerate the exact corpus used in any
  prior demo, given the seed. Demo reproducibility is part of the
  regulator-grade promise.
- Template changes that materially alter the corpus shape are
  visible in the git diff of the templates file, not in a 10 MB CSV
  diff that would have been rubber-stamped.
- A new institution (FINANCIERA_DEMO_003) is created alongside the
  generator so the corpus has three institutions to distribute
  across, which lets the demo show three institutions on the Radar
  view instead of two.
