---
title: Market research — supervisory APIs and complaint-management SupTech comparators
date: 2026-05-15
source: GPT deep research, curated and integrated 2026-05-15
status: Living document — append-only revisions tracked in git history
---

I'll use the project context as the baseline and benchmark it against regulator complaint systems, SupTech architectures, NLP/on-prem AI examples, open-source components, and LatAm precedents. I'll separate directly comparable systems from reusable patterns for an SBS-focused spec or prototype.

I'm narrowing the benchmark toward regulator data regimes with public taxonomies, reporting forms, databases, or APIs, while using official institutional sources first and secondary sources only for gaps.

Thought for 9m 48s

# Market research: supervisory APIs and complaint-management SupTech comparators for SBS Peru

Using your SBS brief as the scope anchor, the closest market benchmark is not a generic complaint-management SaaS platform. It is a mix of: regulator complaint databases, firm complaint-reporting regimes, open-data complaint rankings, SupTech reference architectures, and open-source AI/data components that can be assembled into a vendor-neutral on-prem sandbox. Your project's specific design center is a two-tier API/batch ingestion model mapped to Anexo 1-A, with downstream Radar/Alarm/Workflow analytics, synthetic data only, no live pilot, and all AI on-prem at SBS.

## 1. Executive findings

There is no single public system I found that exactly matches the SBS target architecture: supervised-institution-to-regulator complaint ingestion via both near-real-time API and batch upload, with Peruvian Spanish NLP, proportional treatment for smaller institutions, on-prem LLM agents, and a supervisory Radar/Alarm/Workflow layer. The strongest comparators each cover part of the target:

| Comparator | Closest fit to SBS | Main lesson |
| --- | --- | --- |
| US CFPB Consumer Complaint Database | Public complaint database, public API, complaint taxonomy, company response workflow | Best open reference for complaint data fields, narrative governance, API access, and public transparency |
| Brazil Banco Central complaint ranking | LatAm regulator, open complaint ranking data, institution-level complaint index | Best LatAm model for normalized complaint indicators and public institutional benchmarking |
| UK FCA complaints reporting regime | Firm-submitted complaint returns, taxonomy, reporting modernization, proportional reporting | Best model for a regulator-side complaint reporting return and taxonomy governance |
| Australia AFCA + ASIC IDR reporting | Public complaint Datacube plus mandatory internal dispute-resolution reporting | Useful split between case handling, public benchmarking, and supervisor reporting |
| Mexico CONDUSEF systems | Spanish-language complaint portals, financial-entity workflow, public performance bureau | Best Spanish/LatAm consumer-facing workflow comparator, especially for transparency |

The SBS design is directionally well supported by market practice if it is framed as "single complaint taxonomy + dual ingestion channels + validation + supervisory analytics + human-approved workflow", not as "real-time autonomous AI supervision." That framing matches global SupTech maturity evidence: authorities are prioritizing foundational data infrastructure, workflow automation, API-based reporting, and only then advanced analytics and generative AI.

## 2. Five most directly comparable systems

### 2.1 US CFPB Consumer Complaint Database

The CFPB is the strongest public reference for complaint data publication and API design. Its public database lets users view, filter, map, read, export, and access complaint data through an Open Data API; published data are freely available. Its field reference includes date received, product, sub-product, issue, sub-issue, complaint narrative, company response, company, state, ZIP code, tags, submission channel, company response timing, and complaint ID.

**What SBS should borrow:** CFPB's taxonomy pattern is highly reusable: product → sub-product → issue → sub-issue is conceptually close to SBS's need to operationalize Anexo 1-A across product, channel, motivo, and resolution dimensions. CFPB also provides a strong precedent for narrative governance: complaint narratives are only published with consumer consent and after steps to remove personal information.

**Workflow relevance:** CFPB's complaint process routes complaints to companies, companies generally respond within 15 days, some provide final responses within 60 days, and the consumer can review the company response. That is not identical to SBS institutional reporting, but it is a useful workflow analogue for the "institution response / regulator visibility / consumer protection" chain.

**Where it falls short for SBS:** The CFPB's public API is primarily a data access API, not a published supervised-institution ingestion API. The system is consumer-to-regulator-to-company, while SBS's Part 1 is supervised-institution-to-regulator reporting. Its taxonomy is US-specific and public narrative handling is shaped by US disclosure rules.

#### 2.1.S Synthetic-corpus generation (added Prompt 8 for ADR 0036)

Where CFPB publishes anonymised real complaints, SBS cannot — none have been collected yet under the new regime. The data-fidelity targets that make CFPB's corpus credible to researchers and regulators are the right targets for SBS's synthetic corpus: narrative realism, distribution shape, format-valid identifiers, anonymised PII. SBS generates synthetic data that follows those same fidelity targets.

**Three fidelity tiers** map cleanly onto progressive use cases.

- **Tier 1 — structurally valid only.** Every row passes the schema validator. Narratives are placeholder text. Sufficient for ingestion-pipeline smoke testing.
- **Tier 2 — Tier 1 plus domain authenticity.** Realistic narratives (template-based, parameterised per row), realistic monetary amounts (log-normal over the actual market range), format-valid synthetic identifiers (DNI Modulo-11 checksum, RUC Modulo-11 checksum, Peru mobile pattern). Sufficient for demo credibility and for ingestion smoke testing under load.
- **Tier 3 — Tier 2 plus statistically-realistic distributions.** Four distinct pattern families: (a) heavy-tail per-institution frequency (Pareto-shaped, 80/20 concentration); (b) weekly seasonality with Friday peak (matched against consumer-banking complaint patterns); (c) correlated clusters following synthetic operational incidents (e.g., 200 complaints about one mortgage product over 10 days, simulating an institution-level conduct failure); (d) prudential-versus-conduct pattern distinction — prudential patterns concentrate by counterparty / exposure (sparse but high-impact), conduct patterns spread across many consumers (dense but lower per-incident impact). Sufficient for pattern-detection ML, agent reasoning evaluation, and demo flows that need findings to surface.

**Template-based, not LLM-generated.** Template-with-parameter-substitution gives bit-identical regeneration from `(seed + templates + generator code)`. LLM generation is non-deterministic across model versions, sampling parameters, and prompt drift, and the output is opaque to PR review. Auditability is a regulator-grade concern: a contributor adding inappropriate content to a templates file shows up in diff; the same content in an LLM-prompt change does not.

**Deterministic seeding.** Reproducibility of demo data is part of the regulator-grade promise. A WBG or SBS reviewer should be able to regenerate the exact corpus used in any prior demo given the seed. This follows the OpenSSF reproducible-builds principle applied to data.

This subsection is the load-bearing precedent reference for [ADR 0036](../adr/0036-synthetic-corpus-fidelity-tiers.md).

### 2.2 Banco Central do Brasil complaint ranking

Brazil's Central Bank has a strong LatAm comparator in its Ranking de Instituições por Índice de Reclamações. The dataset consolidates citizen complaints against financial institutions that were received, analyzed, and closed by the Central Bank; it publishes institution-level complaint indexes, counts by complaint type, and customer denominators. The index is calculated using procedent regulated complaints per million customers. The BCB also exposes ranking resources in JSON and CSV and lists complaint rankings dating from July 2014.

**What SBS should borrow:** BCB's normalized complaint index is one of the best public patterns for SBS's Alarm layer. Raw complaint counts are misleading because large banks naturally generate more complaints. BCB's denominator-based index gives SBS a defensible pattern for comparing banks, financieras, insurers, AFPs, and cooperatives proportionally.

**LatAm relevance:** BCB's service explains that the ranking is formed from complaints submitted through Central Bank service channels, with a sample of institutional responses analyzed and complaints classified as procedent when there is evidence of non-compliance. It covers banks, finance companies, payment institutions, and cooperative banks.

**Where it falls short for SBS:** BCB's public system is an open-data ranking and benchmarking tool, not an end-to-end complaint ingestion API or workflow system. It does not provide the narrative-level supervisory analytics pattern SBS is considering.

### 2.3 UK FCA complaints reporting regime

The FCA is the strongest comparator for firm-submitted complaint reporting. The FCA publishes complaints data every six months, including firm-specific and aggregate market-level data, and provides dashboards across opened, closed, upheld complaints, redress, firm type, product, and complaint reason.

The FCA's 2025–2026 modernization is particularly relevant. Its PS25/19 confirms a single unified complaints return, permission-based reporting, simplified nil returns, individual firm-level reporting, an updated complaints taxonomy, contextualized complaints data, vulnerable-customer reporting, fixed six-month reporting periods, and publication thresholds. The FCA states that the reform is intended to reduce duplication, improve consistency, improve benchmarking, and strengthen consumer protection.

**What SBS should borrow:** This is a strong precedent for SBS to position Anexo 1-A as a single consolidated complaints return rather than a fragmented set of institution-specific submissions. FCA's "permission-based reporting" also maps well to SBS's proportionality principle: institutions should submit the sections relevant to their regulated activities and reporting regime.

**Where it falls short for SBS:** FCA's model is periodic reporting, not near-real-time event ingestion. It is also UK-specific and embedded in the FCA Handbook/DISP regime. The value for SBS is the reporting-governance pattern, not the taxonomy content itself.

### 2.4 Australia AFCA Datacube + ASIC internal dispute-resolution reporting

Australia has a split model: AFCA operates an external dispute-resolution complaints environment and publishes an interactive complaints database, while ASIC sets internal dispute-resolution standards and requires many financial firms to report IDR data. AFCA describes its Datacube as an interactive complaints database that makes financial-firm complaint data publicly available, with firm-level complaint data included above defined thresholds and updated regularly. ASIC's RG 271 is an enforceable internal dispute-resolution guide for financial firms and notes that most firms with IDR obligations must report IDR data to ASIC.

**What SBS should borrow:** Australia is useful for distinguishing three layers that SBS should keep separate: consumer complaint handling, firm internal complaint management, and regulator reporting/analytics. This distinction will help avoid scope creep in the SBS sandbox.

**Where it falls short for SBS:** AFCA is not the prudential/market-conduct supervisor; it is an external dispute-resolution body. The Datacube is a public complaints database, not an on-prem supervisory analytics stack.

### 2.5 Mexico CONDUSEF systems

CONDUSEF provides several Spanish-language comparators. Its Portal de Queja Electrónica is an electronic window for users of financial services to submit complaints, which are managed with financial institutions. Its Buró de Entidades Financieras is a public consultation and dissemination tool showing financial institutions' products, fees, user claims, sanctions, abusive clauses, and other performance information; it covers banks, insurers, AFORES, SOFIPOs, SOCAPs, and other sectors. Its REDECO debt-collection system lets people submit complaints against financial institutions and receive responses through the same system; financial institutions onboard through CONDUSEF's institutional identity mechanism and must attend complaints linked to bad debt-collection management.

**What SBS should borrow:** CONDUSEF is useful for Spanish-language UX, institutional identity, complaint tracking, public transparency, and institution response workflows. It is also relevant because its public bureau includes cooperative savings-and-loan institutions, which is directionally useful for SBS's COOPAC concern.

**Where it falls short for SBS:** CONDUSEF's strongest public systems are consumer-facing portals and transparency tools. They are not public examples of a supervised-institution complaint ingestion API with batch/API tiers.

## 3. Secondary comparators worth citing

Colombia's SFC has Spanish-language consumer complaint and conciliation channels. Its public portal lets users report an inconformity with a financial-system entity, which will be attended directly by the financial entity, and separates that from complaints about the SFC's own services. It also has public pages for statistical complaint figures against supervised entities.

Chile's CMF lets users submit claims against banks and financial institutions and request responses about financial products; it also provides an online status-checking mechanism for claims against supervised entities.

Bank of Spain, Banca d'Italia, and BaFin are useful as European transparency comparators, but less directly useful for SBS's API/batch architecture. They publish complaint statistics and annual complaint reports, but the public evidence is weaker for open complaint ingestion standards.

## 4. Two-tier regulatory data collection precedents

The SBS two-tier design is well supported by broader regulatory-reporting practice. The most useful pattern is not "everyone must use an API immediately," but one canonical data model with multiple submission channels.

The ECB's Integrated Reporting Framework is a strong precedent for standardizing reporting obligations across jurisdictions, reducing overlaps, improving data quality, and limiting reporting obligations for small banks to preserve proportionality. The ECB's BIRD initiative is also relevant because it is a free integrated reporting dictionary that describes underlying reporting concepts once, helping banks know which internal data to extract and how to process them.

The EBA's reporting framework provides a governance pattern for validation: reporting requirements are translated into a Data Point Model, with business concepts, relationships, validation rules, and XBRL taxonomies. Authorities can use similar taxonomies for collecting data from institutions.

For smaller or lower-readiness institutions, HMRC's Making Tax Digital is a useful non-financial but highly relevant tiering precedent. HMRC recognizes "bridging software" that connects non-compatible software such as spreadsheets to HMRC systems, while more advanced users can submit through compatible software. This is a strong analogy for SBS Tier 2 batch upload: small COOPACs and smaller financieras should not be forced into API readiness before their operational capacity allows it.

## 5. Technical component market map

### 5.A API and schema layer

For the SBS sandbox, the reusable market pattern is:

OpenAPI + JSON Schema + validation rules + versioned code lists + sample payloads.

OpenAPI is a formal standard for describing HTTP APIs and supports documentation, client-code generation, testing, and vendor flexibility. JSON Schema is the natural companion for payload validation because it defines what a valid JSON document must look like.

For SBS, the public "standards pack" should include:

| Artifact | Purpose |
| --- | --- |
| OpenAPI specification | REST endpoints, authentication assumptions, request/response models |
| JSON Schema | Machine-readable Anexo 1-A complaint payload |
| Code lists | Product, channel, motivo, resolution, institution type, geography |
| Validation rules | Required fields, conditional fields, date logic, duplicate checks |
| Batch manifest | File name, reporting period, institution ID, schema version, row count, hash |
| Sample payloads | One valid API complaint, one batch file, one rejected submission |
| Versioning policy | How SBS changes taxonomy without breaking institutions |
| Error catalogue | Human-readable and machine-readable validation messages |

This would make the SBS prototype more than a UI mockup: it becomes a draft regulatory reporting standard.

**Error-model standard.** Among the regulator APIs surveyed for this work, RFC 9457 "Problem Details for HTTP APIs" (the 2024 republication of RFC 7807, with errata folded in) is the convergent error-envelope standard. UK Open Banking Implementation Entity's standards prescribe RFC 7807-style error responses for institution-facing endpoints; the European Commission's REST API guidelines mandate problem+json for new public services; the UK Government Digital Service publishes problem+json as the documented pattern for GOV.UK APIs; HMRC's Making Tax Digital error model uses a problem-details envelope with stable error codes. The shared pattern across these regulators is: stable machine-readable error codes carried in `type` URIs under a namespace the regulator controls, a human-readable `title` and `detail`, and a `traceId` field carrying the request-correlation identifier for audit. For SBS, this is the minimum viable error envelope; the `type` URI namespace under sbs.gob.pe is an SBS policy decision rather than a technical one.

**Documentation portal rendering.** Rendering an OpenAPI document as a navigable docs portal is a tooling choice downstream of the OpenAPI-as-canonical-contract decision. The three production-grade renderers in current use are Stoplight Elements (used at scale by Stoplight platform customers; renders 3.1 cleanly except for a small set of discriminator-union edge cases), Redoc (open-source, used by GitHub's REST docs and many regulator developer portals), and the newer Scalar project. Swagger UI is older and its 3.1 support has lagged; it remains widely deployed for legacy 3.0 specs. The choice between Stoplight Elements and Redoc is preference-driven for most use cases; the regulator-domain decision is to publish a navigable OpenAPI surface at all, which is the precedent established by the CFPB and FCA developer portals cited in [§2.1](#21-us-cfpb-consumer-complaint-database) and [§2.3](#23-uk-fca-complaints-reporting-regime).

#### 5.A.M Authentication, signing, and rate limiting for regulator-facing APIs

Three protocol layers together form the institutional-API auth chain that this project's Part 3 lands. Each layer has a clear single precedent that the corresponding ADR cites.

**Layer 1 — mTLS for client authentication.** The UK Open Banking Implementation Entity's Read/Write Data API specification requires institutional clients to present an X.509 certificate issued by the Open Banking PKI on every connection. The certificate authenticates the institution at the TLS layer; the bearer token issued downstream authorises operations. The same shape is adopted by Brazil's Open Finance specification (publicly available from BCB), the Australian Consumer Data Right (CDR), and the Saudi Arabian Open Banking framework. The pattern is mature: an institution that the regulator already KYCs holds a private key whose certificate is the regulator-issued credential; the TLS handshake binds every byte on the wire to that institution. RFC 8705 §3 ("Mutual TLS Client Authentication") is the protocol-level reference. For the SBS sandbox, the directly-usable precedent is Open Banking UK: institution-facing API, regulator-issued PKI, CN-as-identifier, optional cert-thumbprint binding to the OAuth token.

**Layer 2 — OAuth 2.0 client_credentials with cert-bound tokens (RFC 8705).** The Open Banking UK Read/Write API Specification §5.2 (Access Tokens) describes the scope shape used by every institutional partner: a small enumerated set of scopes (read/write/upload separation) granted by the token endpoint, each access token is a self-contained JWT with a 5–15 minute TTL, and the token carries the `cnf.x5t#S256` confirmation claim per RFC 8705 §3.1 so a stolen bearer token cannot be replayed from a connection presenting a different certificate. Refresh tokens are not used for client_credentials grants (no end-user to delegate to). The 15-minute TTL is short enough that revocation-by-expiry is sufficient for sandbox-grade operations; production deployments add revocation lists or token introspection where the regulator's operational profile requires it. Open Banking UK has been operating this pattern since 2018 and is the longest-running production reference. Brazil Open Finance, ANZ CDR, and HKMA's Open API specifications adopt the same shape.

**Layer 3 — HMAC request signing.** AWS Signature Version 4 (SigV4) §Task 1 (CreateCanonicalRequest) is the most widely-implemented reference for a body-and-timestamp signing pattern. The canonical request string concatenates the HTTP method, the request target, a timestamp, a body hash, and an identity component, then HMAC-SHA256 signs the result. The shape is also used by Twilio's request validation, Stripe's webhook signing, and GitHub's webhook signing — each of these is a variant with the same underlying contract. For an institutional API the SBS shape is a minimal subset of SigV4: the SBS contract has a fixed header surface, so the "signed headers list" SigV4 canonicalises is not needed; everything else is the same. Replay protection via a server-side per-signature cache with a TTL matched to the timestamp-skew window is the canonical complement to the signing step. The institution identifier is included in the canonical request so a signature is bound to the institution that produced it.

**Rate limiting — Stripe's published pattern.** [Stripe's API rate-limits documentation](https://stripe.com/docs/rate-limits) describes a per-account token-bucket implementation with four response headers (`Retry-After` on 429, plus `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` on every authenticated response). The token bucket is the simplest accounting structure with clearly-defined burst behaviour; the four-header response shape is the convention SDK authors expect. Stripe additionally differentiates test-mode and live-mode account limits, which is the same tier shape applied to a different axis. The two-tier (`large` / `small`) classification the SBS sandbox adopts is the regulator-domain expression of the SBS Conduct department head's proportional-treatment framing for supervised institutions: COOPACs are not held to large-bank traffic ceilings, and large banks are not held to COOPAC ceilings. The Redis token-bucket implementation (Lua-script-atomic per-request decrement) is the canonical pattern documented in Redis's own rate-limiting guidance.

This section is the load-bearing precedent reference for ADRs 0031 (mTLS), 0032 (OAuth scopes), 0033 (rate limiting), and the ADR 0027 amendment landing the full HMAC canonical request contract.

#### 5.A.M.U Supervisor-side user session auth (added Prompt 10 for ADR 0040)

§5.A.M covers institution-to-regulator auth at the network edge — mTLS plus OAuth client_credentials plus HMAC, no end-user identity in the loop. The mirror question — how supervisors *inside* the regulator authenticate to the supervisory UI — has a separate canonical reference family. The institution edge and the supervisor edge are two different perimeters with two different auth chains; conflating them is the failure mode this subsection guards against.

**Authorization Code with PKCE for the interactive login flow.** The IETF OAuth 2.0 Security Best Current Practice (RFC 9700, current as of January 2025) §2.1.1 names Authorization Code with PKCE as the default flow for all interactive applications, including confidential server-side web apps. The Implicit grant is deprecated (RFC 9700 §2.1.2). The Resource Owner Password Credentials grant (RFC 6749 §4.3) is permitted only for trusted first-party clients and explicitly discouraged for new development (RFC 9700 §2.4). The OWASP Application Security Verification Standard (ASVS 5.0) §V3 (Session Management) and NIST SP 800-63B §5 (Federation) sit alongside the BCP as the standards-level reference set.

**Opaque session cookie pointing to a server-side store — tokens never reach the browser.** The OWASP Session Management Cheat Sheet and the OAuth BCP §6.2 both recommend that browser-facing applications never hold OAuth access or refresh tokens in client storage (cookies, localStorage, sessionStorage, indexedDB — none of them). The pattern is: the server issues an opaque session identifier as an HttpOnly + Secure + SameSite=Lax cookie; tokens live in a server-side map keyed by that identifier; the cookie carries no identity material itself, only the lookup key. CSRF protection layers on top via a synchroniser-token pattern (double-submit cookie or header-bound token). This is what 18F's `cg-deck` (Cloud.gov dashboard, publicly-sourced) and Keycloak's own admin console implement; it is also what the OWASP cheat sheet recommends without qualification. Storing tokens in the browser — even in HttpOnly cookies — creates a state where a single CSRF or XSS exposes every token the user holds; with server-side storage, the attack surface is the session cookie only.

**Workforce IdP for the regulator.** The UK's HMRC Making Tax Digital developer hub and the OBIE (Open Banking UK) Directory both deploy an OIDC IdP (Keycloak in some agencies, Auth0 / ForgeRock / PingFederate in others) inside the agency network as the workforce identity layer. The supervisory app is a confidential OAuth client; the IdP federates with the agency's existing SSO at the perimeter. The realm export pattern (Keycloak `--import-realm` flag on Keycloak 22+, or `KC_IMPORT_REALM_PATH`) lets the sandbox realm be reproducible from a committed JSON file. Init-scripts that hit the Keycloak admin API on container startup race the readiness check and fail intermittently — the export-and-import pattern avoids that whole failure mode.

**SSE auth refresh.** When a Server-Sent Events stream's bearer token expires mid-stream, the canonical pattern (the WHATWG EventSource specification, GitHub's Actions log-streaming behaviour, Stripe's CLI event tail) is for the server to terminate the stream and the client to refresh-then-reconnect with the `Last-Event-ID` header — the spec-defined resumption mechanism. The server replays events from the last acknowledged id forward; the React component holding the EventSource preserves its local state across the disconnect-reconnect cycle. The "redirect to login on 401" fallback fires only when the refresh itself fails. Documenting this contract before implementing the SSE topics is what stops WS2's session model and WS7's SSE topic model from drifting into incompatibility.

This subsection is the load-bearing precedent reference for ADR 0040 (supervisor session auth, perimeter split, SSE refresh contract) and ADR 0042 (role-based default landing).

#### 5.A.V Visual design system for regulator-grade interactive UIs (added Prompt 10 for ADR 0041)

§5.A.M.U covers the auth chain; this subsection covers what the supervisor sees once they have signed in. Three precedent families.

**Open government design systems.** The UK Government Digital Service (GDS) and the US 18F / Web Design System teams have both published mature design systems for workforce-facing regulator and government UIs: the [GOV.UK Design System](https://design-system.service.gov.uk/) and the [US Web Design System (USWDS)](https://designsystem.digital.gov/). Both are open-source, accessibility-first (WCAG 2.1 AA enforced as the floor), and explicitly scoped to interactive applications a citizen or civil servant would use to do their job. The Australian Government Design System and Canada.ca's design system follow the same shape. The shared pattern across all four: a small set of semantic colour tokens (not a sprawling palette), a typographic scale anchored to a workhorse open-source typeface (Public Sans for USWDS, GDS Transport for GOV.UK), explicit dark/light mode pairings, and a component library named in terms of *purpose* (Alert, Summary List, Details) rather than appearance (Yellow Box, Bulleted Text). Adopting this naming pattern is what makes "criticality" a token, not a colour.

**Information-dense financial UI references.** Bloomberg Terminal is the classic reference for dense supervisory / market-monitoring screens — fixed-width row geometries, monospace numbers, sparing colour, focus on legibility on a projector across the room. The pattern translates poorly to web SaaS at full saturation ("Bloomberg cosplay"), but several modern web descendants calibrate it well: Datadog's metrics views, Grafana's panel grids, AWS CloudWatch's table-heavy dashboards. In the regulator domain, the CFPB Consumer Complaint Database (§2.1) and the FCA's Data Bulletin both use the same restraint: a single accent colour for "look at this," tabular numerals on every count, and zebra-on-subtle rather than gridlines. The translatable pattern is `font-variant-numeric: tabular-nums` on every numeric column so values don't jiggle as they update, a thin border + subtle zebra rather than gridlines + saturated banding, and a single accent colour reserved for "this is the thing the user needs to look at."

**shadcn/ui as the implementation substrate.** [shadcn/ui](https://ui.shadcn.com/) is a copy-the-source-into-your-repo component library (not a node-modules import) built on Radix UI primitives + Tailwind. Its design tokens are CSS custom properties, which lets a project theme the same components per environment without forking the source. The pattern matches the regulator constraint that the SBS prototype must be vendor-handoff-ready: the components live inside this repo, not as a node-modules dependency that could disappear or change semver licence. Atlassian Design System, IBM Carbon, and Microsoft's Fluent each ship as imported packages — viable for SaaS but a worse fit for a regulator-handed-to-vendor codebase. The shadcn pattern (copied source + Radix primitives + token-driven theming) is the one that lets the same component library serve both the May 25 sandbox and the eventual production overlay without re-implementing the components.

**Severity / status tokens specifically.** Three publicly-documented design systems all encode severity as a *semantic* token rather than a literal colour:

- [IBM Carbon](https://carbondesignsystem.com/) — `Notification` and `Tag` components carry a `kind` prop (`error`, `warning`, `info`, `success`) bound to semantic colour tokens (`$support-error`, `$support-warning`, etc.); the tokens are re-mapped per theme without touching the components.
- [US Web Design System (USWDS)](https://designsystem.digital.gov/components/alert/) — `Alert` ships in four semantic variants (`info`, `warning`, `error`, `success`) each with paired text + background + border colours tuned for WCAG 2.1 AA contrast.
- [Salesforce Lightning Design System](https://www.lightningdesignsystem.com/components/notifications/) — `Toast` and `Notification` define `theme` values (`info`, `success`, `warning`, `error`) that map to status colours through a single token table.

The shared shape across all three: bind components to `--severity-<level>-{bg,fg,border}` (or equivalent), not to literal hex. A single palette tweak after stakeholder review then propagates without grep across the consuming components. Binding directly to a hex value is the failure mode this pattern guards against.

This subsection is the load-bearing precedent reference for ADR 0041 (visual design system on shadcn base, SBS themed).

#### 5.A.M.O Outbound webhook signing (added Prompt 8 for ADR 0035)

Where §5.A.M covers institution-to-regulator signing (inbound), the outbound mirror — regulator-to-institution callbacks — has its own canonical reference family. **Stripe webhooks** is the longest-running production reference: per-account secret, HMAC SHA-256 over a canonical request, timestamp + signature headers, replay-resistance through the timestamp window, exponential-backoff retry, persistent failure recording, optional auto-disable after extended failure. **GitHub webhooks** uses the same primitive with a slightly different header shape. **Twilio request validation** is the same shape applied to incoming SMS/voice events. **Slack event subscriptions** uses an identical HMAC pattern with a different replay-resistance scheme.

The same canonical-request shape should be used in both directions so SDK authors implement one verification routine, not two. The differences are only:

- Which secret is used (inbound vs outbound — stored in separate tables to support independent rotation).
- Which side enforces replay protection (server-side for inbound; institution-side for outbound, since the server is the sender).
- Whether a polling fallback exists (Stripe has none; SBS has `GET /v1/batches/{batch_id}`, which means SBS's outbound retry window can be shorter than Stripe's 3-day default).

**`kid` for key rotation.** Following the JWT `kid` (RFC 7515 §4.1.4) and JOSE patterns, an explicit key identifier on every outbound (and inbound, per the ADR 0027 amendment in Prompt 8) signed request lets the verifier select the right secret from the active/previous slots without trial-decryption. The convention is `kid=<environment>-<version-counter>` (`sandbox-v1`, `prod-v1`, etc.) so an operator reading log lines can tell which secret a request was signed under at a glance.

**SSRF prevention.** The callback URL is an SSRF risk surface: an attacker who can write to the per-institution webhook-config row could direct deliveries at internal services. The standard mitigation set (OWASP SSRF prevention cheat sheet) is:

- Scheme allowlist (HTTPS only).
- Host allowlist or hostname constraint (FQDN required, no IP literals).
- Resolved-IP allowlist (no RFC 1918 private ranges, no loopback, no link-local — including specifically the AWS Instance Metadata Service IP `169.254.169.254` whose 2019 exfiltration patterns are the load-bearing case for the explicit call-out).

Validation runs *before each delivery attempt*, not just at registration — a DNS rebinding attack could make a previously-public host resolve to a private IP at delivery time. Per-delivery resolution is the defence.

This subsection is the load-bearing precedent reference for [ADR 0035](../adr/0035-outbound-webhook-signing-contract.md).

#### 5.A.P Developer portal serving choices (added Prompt 9 for ADR 0037)

§5.A line 141 covers the renderer-choice question (Stoplight Elements vs Redoc vs Scalar vs Swagger UI) and notes the regulator-domain decision is to publish a navigable OpenAPI surface at all, which the CFPB and FCA developer portals established. This subsection extends the framing to cover *how* the renderer is served.

**Self-hosted vs CDN-loaded.** Open Banking UK's developer portal (openbanking.atlassian.net) self-hosts its Read/Write API specification renderer; assets are served from the OBIE-controlled domain, not from a third-party CDN. Brazil Open Finance follows the same pattern — assets are part of the published-spec repository (`github.com/OpenBanking-Brasil/specs-seguranca` and the technical-specs companion repos) and the rendered portal is served from BCB-controlled infrastructure. The Australian Consumer Data Right similarly self-hosts the CDR Register Specification renderer. The convergent pattern across regulator-domain portals is: the regulator publishes the source spec under version control, and the rendered portal is served from regulator-controlled infrastructure rather than from a vendor CDN. The rationale is auditability (the regulator can attest what bytes the portal served at a given timestamp), availability (regulator-controlled infrastructure has the regulator's uptime profile, not a vendor's), and signal (institutions read the self-hosted portal as "this is institutional infrastructure" rather than "this is a vendor's marketing surface").

**Vendoring the renderer.** Self-hosting the *portal* page is one step; vendoring the *renderer assets* (Stoplight Elements / Redoc / Scalar JavaScript bundles) is the strict-vendoring variant of the pattern, applied when the deployment context is air-gapped, regulator-grade-availability, or sufficiently network-constrained that a CDN fallback is unacceptable risk. The cost is ~600 KB of committed JavaScript and a manual re-vendoring step when the renderer upstreams a security fix; the benefit is zero external network dependency at portal-render time. For a regulator-facing portal demonstrated in a controlled venue (Lima, Brasilia, Mexico City) where the venue's wifi is not under the regulator's control, vendoring is the conservative default. The Open Banking UK portal does not fully vendor (it relies on a CDN for some renderer assets), but the OBIE specification repository commits the spec files themselves, so the spec is reproducible even if the rendered portal is briefly unavailable.

**"Try It" interactivity vs static documentation.** Stoplight Elements' default behaviour is documentation-public, "Try It"-requires-credentials, which matches the regulator-domain model: a prospective institutional integrator should be able to read the spec without a credential, but actually invoking a sandbox endpoint requires the full auth chain (mTLS + OAuth + HMAC for SBS). The browser-based "Try It" surface cannot satisfy the mTLS leg of the auth chain in any case, so disabling "Try It" entirely (via `tryItCredentialsPolicy="omit"`) and pointing integrators at the helper + curl flow is the cleaner contract. Open Banking UK takes the same position: the portal is documentation; integration uses the published helper code, the OAuth-Banking PKI test endpoints, and curl.

This subsection is the load-bearing precedent reference for [ADR 0037](../adr/0037-developer-portal-serving-mechanism.md).

#### 5.A.S SDK helper distribution practice (added Prompt 9 for ADR 0038)

When a regulator-facing API ships, the institutional integrator audience faces a verification problem: the API uses HMAC signatures and the integrator must implement signature verification correctly on the receiver side. The signature is straightforward (HMAC SHA-256 over a canonical request) but the canonical-request construction is the dominant failure mode — off-by-one newline, trailing whitespace handling, case sensitivity of headers, choice of body-hash encoding (lowercase hex vs uppercase). The Open Banking UK community has documented this verification-failure pattern extensively in its implementer forums: "translate the Python example to Java by eye" produces subtly wrong implementations at a depressing rate.

**Stripe's published model.** [Stripe's webhook signature verification documentation](https://docs.stripe.com/webhooks/signature) publishes hand-written helpers in 7 first-class languages (Ruby, Python, PHP, Node.js, Go, Java, .NET). Stripe started narrower — Python, Ruby, Node.js — and added languages over time as its customer base grew. The expansion pattern is signal-driven: when a critical mass of integrators in language X arrives, Stripe ships a first-class helper; otherwise integrators use the long-tail path (the published canonical-request shape plus a reference implementation in any of the supported languages). Hand-maintained helpers in every conceivable language is not the model; first-class coverage for what integrators actually use, plus a reference for the rest, is.

**OpenAPI Generator for the long tail.** [OpenAPI Generator](https://openapi-generator.tech/) is the canonical tooling for the long-tail client-SDK generation problem. It accepts an OpenAPI 3.x spec and produces idiomatic client libraries in ~50 languages. The Open Banking UK community's documented experience with OpenAPI Generator is mixed: the generated code is mechanically correct but ergonomically rough — naming conventions don't always match host-language idioms, nullability handling varies by generator, and the Go generator has a known issue with `oneOf` / `anyOf` / discriminator unions that requires a documented workaround. The convergent community pattern is "wrap, never edit" — institutions invoke OpenAPI Generator against the published spec, then write a thin idiomatic wrapper around the generated client. Editing the generated code directly produces unmergeable diffs on regeneration. Berlin Group's PSD2 API spec and Australian CDR both publish OpenAPI Generator recipes for integrators following the same model.

**Webhook verification: reference snippet vs full helper.** For languages where a full helper is not first-class, a ~30-line reference verification snippet is the smallest unit that closes the "translate by eye" failure mode. The snippet is tested against a fixture signed payload in the publisher's CI so it is known to compute the right canonical request, and integrators adapt it to their host language. Open Banking UK ships exactly this shape for Java alongside its OpenAPI Generator recipe. Stripe ships full helpers for all 7 first-class languages and does not need the snippet form.

**Distribution mechanism: registry vs release artifact vs in-repo.** For a v0.x sandbox release, distribution via a versioned tarball attached to a GitHub release is the regulator-domain default (Open Banking UK, Brazil Open Finance, Australian CDR all follow this). PyPI / npm publication adds discoverability but also adds permanent supply-chain responsibility (CVE response, semver discipline, deprecation policy, supply-chain attestation chain). The conservative ordering is: in-repo first, GitHub release once the surface stabilises, public registry once the v1.0 milestone is reached.

This subsection is the load-bearing precedent reference for [ADR 0038](../adr/0038-sdk-helper-scope-and-distribution.md).

#### 5.A.D Standards-pack distribution and provenance (added Prompt 9 for ADR 0039)

A "standards pack" — a single versioned artifact bundling the OpenAPI spec, the JSON schemas, the error catalog, the SDK helpers, the recipes, and a manifest — is the publication unit institutions download to start an integration. The format is convergent across regulator-domain APIs.

**Open Banking UK Read/Write API specifications** publish at [github.com/OpenBankingUK/read-write-api-specs](https://github.com/OpenBankingUK/read-write-api-specs) with tagged GitHub releases per version. Each release contains the OpenAPI YAML files, schema files, swagger-codegen configurations, and supporting documentation. Integrators download via `gh release download` or browser-based file download.

**Brazil Open Finance** publishes equivalent bundles at [github.com/OpenBanking-Brasil](https://github.com/OpenBanking-Brasil) with the same pattern: tagged releases, attached artifacts, semver discipline on the version field. Brazil's pack additionally publishes the error catalog as Markdown (the convergent human-readable choice; YAML or JSON error catalogs are machine-readable but harder for compliance staff to review pre-integration).

**Australian Consumer Data Right** publishes the CDR Standards repository with the same tagged-release model. Versioning discipline is explicit — breaking changes are surfaced in release notes; minor versions add fields; patch versions are corrections.

**Manifest shape.** A `manifest.json` at the top of the pack with provenance fields is the convergent pattern. The minimum-required field set is: pack name, pack version, generation timestamp, git commit, publisher identity, license declaration, list of contained artifacts. Open Banking UK additionally publishes a `portal_url` field linking the offline pack back to the live portal, which lets integrators rediscover updated documentation. The `webhook_signature_version` field (or equivalent) — declaring which version of the signature canonical-request shape the pack documents — is needed wherever the pack includes webhook verification helpers, because a pack downloaded against signature `v1` must not be silently used against signature `v2` server behaviour.

**License declaration in the manifest.** SPDX-conforming license identifiers (`Apache-2.0`, `MIT`, etc.) are the convergent practice. For sandbox-grade publications where the final license is pending legal review, the SPDX `LicenseRef-` prefix mechanism (per the SPDX specification) is the conforming way to carry a non-standard placeholder without breaking SPDX-aware tooling that reads the manifest.

**Integrity vs authenticity.** A `checksums.sha256` file alongside the tarball provides *integrity* — a tampered tarball produces mismatched hashes. It does NOT provide *authenticity* — anyone can publish a tarball with matching checksums. GitHub releases lend authenticity through GitHub's own auth chain (the release was published from a repository owner's account), but the authenticity property does not transit if the pack is mirrored elsewhere. The production-grade upgrade path is [SLSA](https://slsa.dev) provenance attestation (currently at SLSA v1.0) plus [Sigstore cosign](https://www.sigstore.dev) signatures, which provide authenticity that transits with the artifact regardless of where it is hosted. The regulator-domain comparator set treats SLSA + cosign as "expected by v2.0, acceptable to defer in v0.x" — Open Banking UK's pre-2024 releases did not have SLSA attestations; the post-2024 releases do.

**OCI artifact distribution as the upgrade path.** OCI registries (Docker Hub, GitHub Container Registry, Harbor) accept arbitrary artifact types and natively support SLSA attestations and cosign signatures. Publishing the standards pack as an OCI artifact in addition to a GitHub release tarball is the model Brazil Open Finance has adopted for its post-2024 publications and is the documented production-grade target for SBS's Part 11 standards distribution work. For v0.1 sandbox, the GitHub release tarball matches the comparator-set default and is the conservative starting point.

This subsection is the load-bearing precedent reference for [ADR 0039](../adr/0039-standards-pack-v0-1-distribution-and-manifest.md).

### 5.B Event-driven ingestion layer

The vendor-generic event-broker framing in the SBS brief is sound. Kafka, NATS, and RabbitMQ are the three strongest open-source reference families, each with a different profile. Kafka is an open-source distributed event-streaming platform used for data pipelines, streaming analytics, integration, and mission-critical applications. NATS is a lightweight open-source messaging system with pub/sub, request/reply, and persistent streaming through JetStream. RabbitMQ is an open-source messaging and streaming broker supporting open protocols such as AMQP and MQTT and deployment on-premises or in cloud environments.

For SBS, the spec should stay vendor-neutral and say: "event broker / queue / pub-sub layer" rather than naming Kafka or NATS as the target. The architecture should define the behavior: idempotency, audit log, retry policy, validation status, dead-letter queue, duplicate detection, and schema-version enforcement.

#### 5.B.W Async-worker patterns for batch ingestion (added Prompt 8 for ADR 0034)

The §5.B framing above covers the streaming-broker variant of an ingestion layer. The complementary variant for batch / file-upload ingestion is an HTTP-endpoint-plus-async-worker pattern: the institution-facing endpoint accepts the upload, persists the bytes, enqueues a job, and returns 202 with a status endpoint URL; an async worker drains the queue, processes the file, and signals completion via a webhook.

This shape is the regulator-domain default for institutional batch submissions:

- **UK Open Banking** — the batch-submission flow for Confirmation of Payee data accepts the upload, returns a tracking ID, and exposes a status endpoint; the institution polls or receives a webhook.
- **SEC EDGAR** — corporate filings are accepted by EDGAR's `submissions` API, validated asynchronously, and surfaced via the filer's status dashboard. The synchronous validate-on-upload alternative would never scale to 10-K filings with thousands of exhibits.
- **CFPB bulk complaint upload** — institutional bulk submissions follow the same enqueue-and-poll pattern.
- **HMRC Making Tax Digital** — VAT submissions accept the payload synchronously, return a receipt, then process asynchronously with a separate query endpoint for the result.

**Worker-runtime choice.** Async-worker runtimes for asyncio Python cluster into three families:

1. **Celery / RQ** — mature, broker-agnostic, heavier operational footprint. Right for teams that already operate Celery elsewhere.
2. **arq** — purpose-built for asyncio Python, Redis as the broker, lightweight, durable across worker restarts. Right when the stack is already asyncio + Redis and the queue surface is single-purpose.
3. **FastAPI BackgroundTasks** — same event loop as the request handler, not durable. Right only for fire-and-forget work where loss on restart is acceptable. **Not acceptable for regulator-grade ingestion** because a uvicorn restart loses the in-flight batch.

For a stack that already runs Redis (HMAC replay, rate limiting), arq adds the smallest new operational surface. The Celery family is the right answer if the project later needs cross-language workers or if the queue surface grows enough to justify Celery's broker abstraction. APScheduler is *not* in this family — it is cron-shaped (trigger-on-schedule), not queue-shaped (trigger-on-event), and using it for batch dispatch would mean abusing its trigger system.

**Storage durability.** The pattern requires the uploaded file to outlive any single process. Local filesystem is acceptable for sandbox; production object storage (Azure Blob, S3) with lifecycle policies is the production-grade endpoint. The transition from local filesystem to object storage is a configuration change (storage backend abstraction), not a workflow change.

**Concurrency model.** FIFO single-queue is the simplest model; per-institution queue partitioning is the next step up; per-institution worker pools is the production-grade endpoint. The progression matches institutional load growth and is the right ladder for a regulator deployment.

**Validation pipeline reuse.** The async worker should share the per-row validation pipeline with the synchronous per-request endpoint. Two parallel validation paths create a drift surface where Tier 1 and Tier 2 can diverge silently. A test that asserts class identity (the *same Python object*) between the two paths is the standard defence.

This subsection is the load-bearing precedent reference for [ADR 0034](../adr/0034-batch-ingestion-architecture.md).

### 5.C NLP for Spanish complaint narratives

The best open-source Spanish model starting points are BETO and RoBERTa-BNE, not a generic English FinBERT. BETO is a Spanish BERT model trained on a large Spanish corpus and released with TensorFlow and PyTorch checkpoints. RoBERTa-BNE is a Spanish masked-language model pre-trained on 570GB of clean, deduplicated text from the Biblioteca Nacional de España's web crawls, and is intended to be fine-tuned for downstream tasks such as text classification and named-entity recognition.

There are finance-language Spanish sentiment models, but they are not complaint classifiers. For example, Finance Sentiment ES is based on Spanish BERT and trained for Spanish financial-news sentiment, producing positive/negative/neutral labels. It may be useful as a demonstration baseline, but it should not be presented as ready for Peruvian complaint classification.

For complaint-specific prior art, two items are useful. First, ConsumerBR is a 2026 Brazilian Portuguese corpus of more than 3.1 million consumer-company complaint interactions, with anonymized text and structured metadata, built from public Brazilian consumer data. Second, a 2025 customer-service classification paper used classical ML and BERT fine-tuned with LoRA on more than 18,000 complaints and requests across 11 classes, reporting that BERT improved performance over logistic regression, SVM, and XGBoost.

For SBS, the practical recommendation is:

- Start with BETO and RoBERTa-BNE as Spanish baselines.
- Fine-tune only on SBS-approved labeled examples later; for the sandbox, use synthetic and SME-designed examples.
- Treat Peruvian Spanish, SBS product vocabulary, COOPAC terminology, AFP terminology, and complaint motivos as domain adaptation issues.
- Use active learning and human review rather than pretending a generic Spanish model can classify Peruvian financial complaints out of the box.

### 5.D Predictive risk scoring and explainability

The SBS classical ML stack of BERT + XGBoost + SHAP is defensible. XGBoost is an optimized, portable gradient-boosting library that supports machine-learning algorithms under the gradient-boosting framework. SHAP is a game-theoretic method for explaining model outputs through Shapley values and local explanations.

For SBS, the most defensible use case is decision support, not automated enforcement. SHAP can support internal explanations such as: "This complaint was prioritized because of product type, institution history, vulnerable-consumer flag, unresolved status, prior similar complaints, and abnormal volume." It should not be described as a complete legal explanation by itself. Recent supervisory AI guidance emphasizes governance, explainability, bias mitigation, adequate resources, data quality, privacy, and security.

### 5.E On-prem / sovereign agentic layer

The on-prem constraint is consistent with current concerns around data privacy, data security, data localization, and vendor dependency in supervisory AI. For local serving, vLLM is a strong open-source serving layer because it supports high-throughput LLM inference, structured outputs, tool calling, reasoning parsers, an OpenAI-compatible API server, and multiple hardware backends.

For open-weight models, Mistral's published model page is useful because it identifies free open-weight models available under Apache 2.0, including models positioned for coding agents, compact enterprise use, and multilingual reasoning. Model choice should still go through legal, security, and evaluation review; "open weight" does not automatically mean "safe for confidential supervisory data."

For agent orchestration, LangGraph, AutoGen, and Semantic Kernel all support the SBS approval-queue concept. LangGraph is especially relevant because it focuses on long-running stateful agents, durable execution, streaming, persistence, and human-in-the-loop workflows. AutoGen explicitly supports human feedback during agent runs through a UserProxyAgent and recommends this pattern for short approval/disapproval interactions. Semantic Kernel's agent framework supports modular agents, multi-agent collaboration, human-agent collaboration, and process orchestration across tools and APIs.

For SBS, the agentic layer should be scoped as: retrieve, summarize, draft, explain, recommend, and queue for approval. It should not decide, enforce, notify institutions, or escalate without a human approver.

### 5.F Dashboards: Radar, Alarm, Workflow

The Radar/Alarm/Workflow triad is well aligned with SupTech market-monitoring practice. CGAP describes market monitoring as a broad supervisory activity that supports trend analysis, benchmarking, risk-based supervision, and the detection of emerging consumer risks. The World Bank's market-conduct SupTech note highlights APIs and automated dataflows for standardized reporting, complaints management systems, and advanced analytics on unstructured complaint text as relevant tools for market-conduct supervision.

For open-source dashboarding, Apache Superset is a strong candidate for non-SaaS visualization. It is an open-source data exploration and visualization platform with dashboards, SQL exploration, database connections, geospatial charts, and 40+ visualization types.

For SBS, the clean separation is:

| SBS concept | Function | Comparable pattern |
| --- | --- | --- |
| Radar | Continuous surveillance by institution, product, channel, geography, motivo | CFPB trends/maps, FCA dashboards, BCB ranking |
| Alarm | Thresholds, outliers, abnormal increases, repeated unresolved patterns | BCB normalized complaint index, FCA benchmarking |
| Workflow | Case review, supervisory action tracking, agent-drafted memos, approvals | CFPB routing/company response, CONDUSEF/REDECO response tracking |

## 6. Publications and prior art to cite in the SBS report

The most relevant references for the final SBS report are:

| Source | Why it matters for SBS |
| --- | --- |
| World Bank market-conduct SupTech work | Explicitly connects APIs, automated dataflows, complaints management systems, and text analytics for market conduct supervision. |
| Cambridge State of SupTech 2025 | Shows authorities are moving stepwise: data infrastructure, workflow automation, API reporting, then advanced analytics and GenAI. |
| BIS Working Paper 1309, 2025 | Finds that integrated digital/data/SupTech strategies and dedicated SupTech units help authorities move from experimentation to deployment. |
| BIS FSI Insights 73, 2026 | Useful for AI data governance: privacy, quality, security, third-party dependency, and supervisory expectations. |
| IMF AI Projects in Financial Supervisory Authorities, 2025 | Useful for project governance, explainability, bias, stakeholder collaboration, and resource planning. |
| World Bank / CEPR AI in EMDE supervision, 2025 | Directly relevant to emerging-market supervisors; notes cautious use of AI agents, complaints analysis, and the principle that AI should not replace supervisory judgment. |
| BIS Project Ellipse | Strong reference for integrated structured/unstructured data, advanced analytics, early-warning indicators, and prudential metrics. |
| BIS Project Aurora | Useful for synthetic/simulated proof-of-concept design, privacy-enhancing technologies, and cross-institution analytics, even though the domain is AML rather than complaints. |

The most directly relevant Peru-specific prior art I found is Cambridge SupTech Lab's case study listing for a Financial Market Monitoring via Social Media and Web Extraction Advanced Analytics Platform with SBS Peru, Financial Network Analytics, and Winnow Technologies. That is not the same as complaint ingestion, but it is directly relevant to the Radar idea and provides a local SupTech precedent for SBS.

## 7. Public complaint taxonomies or APIs SBS can borrow from

The best public standards to borrow from are:

- CFPB field reference and API documentation for complaint fields, product/issue hierarchy, narrative handling, company response fields, submission channel, timeliness, and complaint ID.
- FCA complaints reporting modernization for unified returns, permission-based reporting, nil returns, individual-firm reporting, updated taxonomy, vulnerable-customer data, six-month reporting periods, and publication thresholds.
- BCB complaint ranking dataset for normalized institution-level complaint indexes and denominator-based benchmarking.
- EBA DPM/XBRL/validation-rule governance for disciplined reporting taxonomy, validation rules, and versioned technical packages.
- ECB BIRD/IReF for a free reporting dictionary, proportionality, and reduction of reporting burden.
- HMRC bridging-software pattern for institutions not ready for direct API integration.

For SBS, this suggests the most credible standards package is: Anexo 1-A as the canonical dictionary, an OpenAPI spec for Tier 1, a batch schema for Tier 2, validation rules, code lists, sample data, and versioning rules.

## 8. LatAm and COOPAC-specific findings

The strongest LatAm comparators are Brazil BCB, Mexico CONDUSEF, Colombia SFC, and Chile CMF. Brazil is strongest for normalized complaint ranking; Mexico is strongest for Spanish-language consumer workflow and public institutional transparency; Colombia and Chile are useful for Spanish-language complaint intake/status processes.

For cooperative relevance, Brazil's BCB ranking includes cooperative banks, while Mexico's Buró de Entidades Financieras includes Sociedades Cooperativas de Ahorro y Préstamo. These are not the same as Peru's COOPAC sector, but they are useful regional evidence that public complaint benchmarking can include cooperative or cooperative-like financial institutions.

I did not find a public Peruvian Spanish financial-complaint NLP model, a public COOPAC-specific complaint API, or a LatAm regulator-published supervised-institution complaint ingestion API that can be copied directly. The practical implication is that SBS should treat the Peruvian Spanish classifier and the COOPAC proportionality design as original project contributions, while borrowing governance and architecture patterns from the comparators above.

## 9. Design implications for SBS

The market research supports the current SBS architecture, with several refinements.

**First, keep the two-tier model.** The API tier is appropriate for large banks and technically mature institutions. The batch tier is not a compromise; it is a proportionality feature. HMRC's bridging-software precedent and ECB/IReF proportionality support this framing.

**Second, make Anexo 1-A the product, not just a reference.** The reusable deliverable should be a machine-readable taxonomy and validation pack: JSON Schema, code lists, validation rules, OpenAPI endpoints, batch manifest, sample payloads, and an error catalogue. This aligns with EBA-style reporting taxonomy governance and CFPB-style public field clarity.

**Third, include normalized complaint indicators.** BCB's complaint index pattern is directly useful for SBS Alarm dashboards. SBS should avoid ranking institutions by raw complaint counts alone; it should normalize by customer base, product volume, complaint regime, institution type, and possibly exposure.

**Fourth, separate private supervisory analytics from public transparency.** CFPB and BCB show the value of public data, but SBS's current prototype is correctly scoped as a sandbox using synthetic data. Public dashboards should be a future governance decision, not a prototype assumption.

**Fifth, describe AI as supervisory support.** The classical ML stack should prioritize triage, clustering, anomaly detection, and explainable risk scoring. The agentic layer should retrieve regulations, summarize patterns, draft memos, and prepare supervisory action suggestions for approval. It should not autonomously decide supervisory actions. This aligns with emerging-market supervisory AI guidance emphasizing human judgment and final authority.

**Sixth, use the five-agent approval queue as a governance demonstrator.** It is a good prototype pattern if it is described as a sandbox workflow showing how human review could work. It should be paired with audit logs, reviewer identity, rationale capture, rollback, prompt/version tracking, and model-output disclaimers. LangGraph, AutoGen, and Semantic Kernel all support human-in-the-loop patterns that can justify this design.

**Seventh, make the architecture vendor-generic but implementation-plausible.** The deck can say "event broker," "schema registry," "validation service," "analytics service," "workflow queue," "local LLM inference," and "dashboard layer." In backup notes, cite Kafka/NATS/RabbitMQ, vLLM, Superset, SHAP, XGBoost, BETO, and RoBERTa-BNE as examples — not commitments.

## 10. Recommended positioning for the SBS report

A defensible market-research conclusion could be written as:

> International comparators show that leading supervisors and consumer-protection authorities increasingly combine standardized complaint taxonomies, digital submission channels, public or internal benchmarking dashboards, and analytics over complaint trends. The SBS proposal is consistent with this direction but adds two locally important features: proportional two-tier ingestion for institutions with different technical capacities, and on-prem AI governance for sensitive complaint data. The closest references are CFPB for complaint data fields and API access, BCB for normalized complaint rankings, FCA for firm-level complaint reporting modernization, CONDUSEF for Spanish-language complaint workflow and public transparency, and BIS/World Bank/Cambridge SupTech work for the broader supervisory-analytics architecture.

---

This document covers the regulator-domain comparator landscape only. Operational precedents for the platform's tooling (supply chain, scanners, SBOM format, environment-variable handling) are in [supply-chain-precedents.md](supply-chain-precedents.md). Both files are valid citation targets for ADR Precedent sections; see [docs/research/README.md](README.md) for the citation rule.
