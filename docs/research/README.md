# Research index

This directory holds the comparator research that anchors the project's design decisions. North-star principle 6 (CLAUDE.md): every major design decision cites a comparator from [market-comparators.md](market-comparators.md). The `benchmark-checker` subagent enforces this.

## Files

- [market-comparators.md](market-comparators.md) — primary research document. Comparators across CFPB, FCA, BCB, EBA, ECB, HMRC, BIS, World Bank, CGAP. Cite specific sections, not the document as a whole.

## How to cite

In an ADR, PLAN.md design section, or any user-facing spec, use this pattern:

```markdown
## Precedent

- <Comparator> (docs/research/market-comparators.md §X.Y) — what they do, what we adopt.

## Divergence

- Where SBS departs and why.
```

If `market-comparators.md` does not yet cover a topic, the author has three options:

1. Commission research to extend the document.
2. Cite the closest analogue and label it as such ("closest analogue: BIS Innovation Hub …").
3. Declare the design exploratory and accept higher second-opinion scrutiny.

## Comparator → PLAN.md cross-reference

Section numbers below refer to headings inside [market-comparators.md](market-comparators.md). Cite `docs/research/market-comparators.md §X.Y` in ADRs and design docs; `benchmark-checker` enforces specificity.

| Comparator | Section in market-comparators.md | Primary PLAN section(s) | Primary ADR(s) | What we borrow |
| --- | --- | --- | --- | --- |
| US CFPB Consumer Complaint Database | §2.1 | Part 2 (taxonomy), Part 11 (Standards Pack) | ADR 0002, 0004 | Field reference, product/sub-product/issue/sub-issue hierarchy, narrative governance |
| Banco Central do Brasil — complaint ranking | §2.2, §5.F | Part 8 (per-institution ops dashboards), Part 11 (taxonomy distribution) | ADR 0011 | Normalized complaint index (per-million-customers denominator) for Alarm layer |
| UK FCA complaints reporting regime — PS25/19 | §2.3, §4 | Part 4 (Tier 2 batch), Part 11 (Standards Pack) | ADR 0005, 0013 | Unified return, permission-based reporting, taxonomy modernisation |
| Australia AFCA Datacube + ASIC RG 271 | §2.4 | Part 8 (per-institution ops) | ADR 0011 | Three-way split: consumer handling / firm internal / regulator reporting |
| Mexico CONDUSEF (Portal de Queja, Buró, REDECO) | §2.5, §8 | Part 7 (onboarding), Part 8 (Spanish-language UX) | ADR 0011 | Spanish-language consumer workflow, institution identity, public transparency patterns |
| Colombia SFC, Chile CMF | §3 | Part 8 (Spanish-language UX) | — | Spanish-language complaint intake and status |
| ECB Integrated Reporting Framework / BIRD | §4 | Part 2 (taxonomy), Part 11 (Standards Pack) | ADR 0002, 0013 | Single canonical data dictionary; proportionality |
| EBA DPM / XBRL / validation rules | §4, §5.A | Part 2, Part 11 (Standards Pack) | ADR 0013 | Validation-rule governance, versioned technical packages |
| HMRC — Making Tax Digital "bridging software" | §4 | Part 4 (Tier 2 batch as proportionality), Part 7 (SDK + conformance) | ADR 0005, 0010 | Tier 2 batch is a proportionality feature, not a compromise |
| OpenAPI + JSON Schema + validation pack | §5.A | Part 2, Part 3, Part 7, Part 11 | ADR 0004, 0010, 0013 | Standards pack shape: spec + schema + code lists + rules + samples |
| Kafka / NATS / RabbitMQ (vendor-neutral framing) | §5.B | Part 1 (event bus) | — | Behaviour-not-vendor framing for the event broker |
| BETO / RoBERTa-BNE | §5.C | Part 5 (ML substrate) | ADR 0006 | Spanish-language baselines for complaint classification |
| XGBoost + SHAP | §5.D | Part 5 (ranker + explainability) | ADR 0006 | Decision support, not automated enforcement |
| vLLM + open-weight models | §5.E | Part 1 (vLLM serving), Part 5 | ADR 0001 (three-layer) | On-prem serving precedent |
| LangGraph / AutoGen / Semantic Kernel — human-in-the-loop | §5.E | Part 6 (agent infrastructure) | ADR 0007, 0009 | Approval-queue pattern with durable execution |
| Apache Superset / dashboarding | §5.F | Part 8 (dashboards) | — | Open-source visualisation precedent |
| BIS Innovation Hub — Ellipse, Aurora | §6 | Part 5 (ML), Part 10 (AI/ML eval) | ADR 0006, 0012 | Integrated structured + unstructured analytics; synthetic-data PoC design |
| World Bank market-conduct SupTech | §6, §9 | Part 9 (handoff), Part 10 (eval framing) | ADR 0012 | Market-conduct supervision pattern: APIs + complaints + text analytics |
| Cambridge State of SupTech 2025 | §6 | Cross-cutting (sequencing) | — | Sequence: data infra → workflow → API reporting → analytics → GenAI |
| BIS FSI Insights 73 (2026), IMF AI in supervision (2025), CGAP — Responsible AI | §6, §9 | Part 5, Part 10 (AI/ML eval framework) | ADR 0006, 0012 | AI governance: privacy, quality, security, third-party, human-in-loop |
| Cambridge SupTech Lab — SBS Peru market-monitoring case | §6 | Cross-cutting (Peru prior art) | — | Local SupTech precedent for Radar concept |

Notation: a missing comparator for a Part means we do not yet have one on file — flag it and consider extending the research document, or accept "exploratory" status per `benchmark-checker` guidance.

## Maintenance

When [market-comparators.md](market-comparators.md) is edited:

1. Update the table above if section numbers shift.
2. Re-run `benchmark-checker` against the ADRs that cite the moved sections.
3. Add a one-line entry to [docs/DECISIONS.md](../DECISIONS.md) noting the research update.
