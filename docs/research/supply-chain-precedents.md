---
title: Supply chain, secrets, and software-provenance precedents
date: 2026-05-16
source: Initial set distilled during Prompt 2 (Part 1, supply chain & secrets), drawing on widely-known open-source security practice and public-sector repository conventions.
status: Living document — append-only revisions tracked in git history
---

# Supply chain, secrets, and software-provenance precedents

This document collects the operational precedents the platform's tooling is built on: secret scanners, dependency-update tooling, SBOM format, dependency-review thresholds, environment-variable handling, image signing, provenance attestation, and related supply-chain decisions. It is the citation target for ADRs that lock infrastructure-of-the-build decisions — distinct from [market-comparators.md](market-comparators.md), which covers the regulator-domain comparator landscape (CFPB, BCB, FCA, AFCA, CONDUSEF, etc.).

Both files are valid citation targets for ADR `## Precedent` sections. The `benchmark-checker` subagent accepts a citation pointing to a specific section of any research file under `docs/research/`. The rule is specificity — name the section and the comparator — not the filename.

## 1. Secret-scanner stacks

The two-scanner pattern (gitleaks for high-confidence pattern matches, detect-secrets for entropy-plus-baseline) is the default in mature open-source security tooling. Yelp built and open-sourced `detect-secrets` to enforce a baseline-aware scan at commit time; the project explicitly addresses the "every UUID is a false positive" failure mode by gating findings against a committed baseline. `gitleaks` is the de-facto match for high-signal pattern detection (AWS keys, GitHub tokens, JWTs, Slack tokens) and is widely used in open-source infrastructure repositories, including in CI on repos such as `cilium/cilium` and several Kubernetes SIG repos. CFPB's open-source projects on github.com/cfpb run gitleaks in CI. The common pattern is: both scanners locally, gitleaks-only in CI, detect-secrets baseline committed as a developer aid.

## 2. Dependency update tooling in regulator / government repos

GitHub-native Dependabot is the default in comparable public-sector repos: US 18F (`18F/*`), UK Government Digital Service (`alphagov/*`, including GOV.UK Pay and Notify), UK HMRC's open-source organisation (`hmrc/*`), Canada's CDS (`cds-snc/*`), and Singapore GovTech (`opengovsg/*`). Renovate is the strong alternative and is preferred in some commercial fintech contexts, with the trade-off being more configuration surface area in exchange for finer-grained scheduling and grouping. The pattern in regulator-facing repos is to start with Dependabot and migrate to Renovate only when grouping or scheduling demands exceed what Dependabot can express.

## 3. SBOM format

CycloneDX (OWASP) and SPDX (Linux Foundation) are the two practical choices. CISA's "Minimum Elements for a Software Bill of Materials" (2021) is format-neutral, but the supporting tooling ecosystem has consolidated around CycloneDX JSON in OpenSSF-funded projects, in Anchore's `syft` (which emits both formats but defaults to CycloneDX), and in Sigstore's release artifact attestations. The German BSI's "Technical Guideline TR-03183" recognises both. CycloneDX JSON, produced by `syft`, is the most-supported pipeline shape — Trivy, Grype, Dependency-Track, and OpenSSF Scorecard all consume it without an adapter. This is the format the SBS handoff package will produce.

## 4. Dependency-review thresholds

GitHub's `dependency-review-action` exposes a `fail-on-severity` knob with values `low`, `moderate`, `high`, `critical`. The defensible threshold for a pre-pilot codebase is `high`: blocking on `moderate` produces enough false-positive friction (transitive-only, advisory-not-applicable) to push contributors to skip the gate, which is worse than letting moderates through with visibility. Several CFPB and UK GDS open-source repos use `high` as their default; production-tier projects tighten the bar to `moderate` once the noise floor is understood. The threshold is a parameter, not a posture; SBS revisits it at Part 9.

## 5. Environment-variable / secret handling

The 12-factor app methodology (factor III, "Config") is the foundational precedent for `.env`-style configuration: secrets in environment, never in code, never in version control. GitHub's own "About secret scanning" guidance and "Managing encrypted secrets in your repository and organization" pages codify the modern enforcement layer: gitignore the `.env`, scan for committed secrets, store CI-time secrets in the platform's encrypted-secret store, and rotate on exposure. The CFPB, FCA, and HMRC open-source repos follow this pattern uniformly. SBS's contribution here is per-tool wiring (Azure OpenAI four-variable shape, WBG ITS tenancy), not a new posture.

## Future sections

As tooling decisions are locked, additional sections will be appended:

- **6. Image signing.** Sigstore / cosign adoption patterns in regulator-adjacent OSS. Locked in Part 9.
- **7. Provenance attestation.** SLSA framework levels and what attestations OpenSSF Scorecard checks. Locked in Part 9.
- **8. License-compliance scanning.** ScanCode, FOSSA, or `syft`-derived license metadata against an approved-list policy. Locked in Part 9.
- **9. Container scanning.** Trivy / Grype in CI against a vulnerability-database freshness policy. Locked in Part 9 once images exist.

Append-only edits below this line tracked in git history.
