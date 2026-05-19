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

**Rate limiting — Stripe's published pattern.** [Stripe's API rate-limits documentation](https://stripe.com/docs/rate-limits) describes a per-account token-bucket implementation with four response headers (`Retry-After` on 429, plus `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` on every authenticated response). The token bucket is the simplest accounting structure with clearly-defined burst behaviour; the four-header response shape is the convention SDK authors expect. Stripe additionally differentiates test-mode and live-mode account limits, which is the same tier shape applied to a different axis. The two-tier (`large` / `small`) classification the SBS sandbox adopts is the regulator-domain expression of Mariela's proportional-treatment framing for supervised institutions: COOPACs are not held to large-bank traffic ceilings, and large banks are not held to COOPAC ceilings. The Redis token-bucket implementation (Lua-script-atomic per-request decrement) is the canonical pattern documented in Redis's own rate-limiting guidance.

This section is the load-bearing precedent reference for ADRs 0031 (mTLS), 0032 (OAuth scopes), 0033 (rate limiting), and the ADR 0027 amendment landing the full HMAC canonical request contract.

### 5.B Event-driven ingestion layer

The vendor-generic event-broker framing in the SBS brief is sound. Kafka, NATS, and RabbitMQ are the three strongest open-source reference families, each with a different profile. Kafka is an open-source distributed event-streaming platform used for data pipelines, streaming analytics, integration, and mission-critical applications. NATS is a lightweight open-source messaging system with pub/sub, request/reply, and persistent streaming through JetStream. RabbitMQ is an open-source messaging and streaming broker supporting open protocols such as AMQP and MQTT and deployment on-premises or in cloud environments.

For SBS, the spec should stay vendor-neutral and say: "event broker / queue / pub-sub layer" rather than naming Kafka or NATS as the target. The architecture should define the behavior: idempotency, audit log, retry policy, validation status, dead-letter queue, duplicate detection, and schema-version enforcement.

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
