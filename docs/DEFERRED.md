# Deferred work

This document tracks decisions and implementations deliberately postponed, with a target Part for revisit. Every entry must have: what was deferred, why, target Part, where the deeper trail lives (issue, ADR, session journal).

Reviewed at the end of each Part. Anything still here at the start of Part 9 (production readiness) is either a Part 9 task or a knowingly-accepted permanent gap.

## Active deferrals

### CI: secret-scanner action vs. binary
- **Status:** Implemented binary-only in PR #7.
- **Why deferred:** `gitleaks-action@v2` requires a paid org license; the binary is free and equivalent for our needs.
- **Open question:** Is the licensed wrapper's value (PR comments, summary reports) worth the cost long-term?
- **Target Part:** 9.
- **Trail:** issue #9, ADR 0016 Amendment 2026-05-16.

### CI: dependency vulnerability scanning
- **Status:** Removed in PR #7.
- **Why deferred:** `dependency-review-action@v4` requires GitHub Advanced Security; not licensed for `WBG-ITS-Innovation` org.
- **Open question:** Procure GHAS, or implement `pip-audit` + `npm audit` workflows ourselves?
- **Target Part:** 9.
- **Trail:** issue #8, ADR 0019 Amendment 2026-05-16.

### Zscaler / corporate-proxy doc verification
- **Status:** `docs/setup/corporate-proxy-and-zscaler.md` marked DRAFT in PR #7.
- **Why deferred:** Requires a WBG colleague to run through it on a clean machine.
- **Target Part:** No specific Part — happens whenever a colleague onboards.
- **Trail:** Doc's own "Open questions" section, Prompt 2 session journal.

### gitsign / signed commits
- **Status:** Closeout warns "gitsign not configured; committing unsigned" each time.
- **Why deferred:** Originally targeted at Part 2; Part 2's current scope is the Data Model & API Skeleton, which is the wrong owner-Part. Re-homed during Prompt 3.
- **Target Part:** To be assigned within Part 1 — owner-prompt picked once tooling (Prompt 4) and Docker Compose (Prompts 5–7) land and the signing-vs-CI dependency surface is clear.
- **Trail:** Prompt 1 journal, Prompt 2 journal, Prompt 3 journal.

### Branch protection: required-approvals set to 0
- **Status:** `main` branch protection has `required_approving_review_count: 0`.
- **Why deferred:** Solo work cannot self-approve. Setting it to 1 today would block every PR.
- **Action needed:** Bump to 1 when a second human joins the repo as a collaborator with review rights.
- **Target:** When a second human reviewer is added as a collaborator. Not Part-bound; happens at the personnel event.
- **Trail:** This entry.

### Closeout: `--slug` symmetry with `--prompt`
- **Status:** `--slug` is still inferred from the branch name via `infer_slug_from_branch` with a default fallback of `workflow-harness`. `--prompt` was made required in Prompt 3 (carry-over fix #1) but `--slug` was not made symmetric.
- **Why deferred:** Prompt 3's adversarial review surfaced this. The branch-name hook already rejects non-conforming names at push time, so the silent-fallback failure mode is bounded — but it can still emit a wrong slug into the cross-review filename, journal slug field, and PR title if the operator runs from a misnamed branch.
- **Action when triggered:** Either make `--slug` required (matching `--prompt`), or hard-fail when `infer_slug_from_branch` falls back to the default while `--slug` was not supplied. Add a `test_close_prompt_refuses_branch_without_part_prefix` regression test.
- **Target:** Before Prompt 4 closeout.
- **Trail:** Prompt 3 session journal, second-opinion review.

### Cross-review: `enforce_sections` ↔ `check_triage_filled` contract mismatch on `## Triage`
- **Status:** Three sibling bugs in the writer/reader contract between `cross_review.py:enforce_sections` (writer) and `close_prompt.py:check_triage_filled` (reader) on what counts as a `## Triage` heading.
  - **(a) Substring writer vs. line-prefix reader.** The writer injects the placeholder on `"## Triage" in <line>` (substring `in`); the reader picks the LAST `line.startswith("## Triage")` match. The two rules disagree on what a heading is.
  - **(b) `startswith` false positives.** `line.startswith("## Triage")` matches `## Triage rationale`, `## Triage Notes`, `## Triage and disagreements`, or any heading the model invents that begins with the word "Triage". A model that emits both a canonical `## Triage` AND a later `## Triage rationale` defeats the gate: the writer sees the canonical one and injects the marker; the reader's `startswith` matches both and picks the LAST, which may be the rationale section without the marker. Gate green-lights an unreviewed file. Sibling failure: a sufficiently-instructed model emits its own dispositioned `## Triage` section (violating the SYSTEM_PROMPT instruction to leave it blank); writer sees the existing TODO/"fill in" absence and skips the injection.
  - **(c) Byte-offset writer insertion, not line-anchored.** `enforce_sections` does `out = out[:idx] + "## Triage\n\n_TODO..._\n"` where `idx = out.index("## Triage")`. If the substring "## Triage" appears mid-line inside model prose (e.g. an unclosed inline code-span quoting the heading literal), the injected `## Triage` placeholder lands mid-line, not at line-start. The line-anchored reader then correctly reports "no `## Triage` section" — but only because the new section-anchored gate (Prompt 3) catches it. The old whole-file substring check would have silently passed on the malformed file. Surfaced during Prompt 3 closeout against this very PR — Azure (gpt-5.4) truncated mid-sentence while quoting the literal `## Triage` token in its parser-brittleness finding, and `enforce_sections` mangled the injection.
- **Why deferred:** All three siblings surfaced via Prompt 3's adversarial review + the Prompt 3 closeout run itself. The current SYSTEM_PROMPT explicitly tells the model not to fill the Triage section, and (b) requires a model that invents a `## Triage <suffix>` heading. (c) requires a model that quotes `## Triage` mid-prose AND truncates before closing context; today's Azure run hit exactly that. Same class of bug — writer/reader heading-shape contract — so deferring all three to one fix with one shared regression fixture is cheaper than three cascading in-prompt fixes.
- **Action when triggered:** Make writer and reader agree on an exact, case-insensitive, trailing-whitespace-tolerant heading match: `line.rstrip().lower() == "## triage"`. Update both `enforce_sections` (writer) and `_extract_last_triage_section` (reader) to share this rule. In `enforce_sections`, switch from byte-offset insertion (`out[:idx] + ...`) to line-anchored insertion: locate the line whose stripped/lowercased content equals `## triage` and rewrite from that line forward; if no such line exists, append a freshly-anchored `\n\n## Triage\n\n_TODO..._\n` block at EOF. Have `enforce_sections` overwrite the `## Triage` body unconditionally with the placeholder (or wrap any model output with `_TODO: human-filled — model proposed: <verbatim>_`) to close sibling (b). Add one shared regression fixture in `tests/test_close_prompt.py` named `test_triage_writer_reader_contract_handles_heading_shape_drift` covering all three siblings: (i) model emits its own dispositioned `## Triage`; (ii) model quotes `## Triage` mid-sentence inside an inline code span; (iii) heading-shape variants — `## TRIAGE` (case), `## Triage  ` (trailing whitespace), `## Triage rationale` (suffix), `### Triage` (h3 — must not match).
- **Target:** Before Prompt 4 closeout.
- **Trail:** Prompt 3 session journal, second-opinion review. Third sibling surfaced during Prompt 3 closeout — Azure cross-review quoted `## Triage` mid-prose, exercising the malformed-file branch of `check_triage_filled` for the first time.

### ADR 0023 dependency-placement subsection
- **Status:** ADR 0023 documents the workspace layout but does not say which `pyproject.toml` an API-only dependency should land in while members carry `package = false` stubs. A contributor who adds `fastapi` in Part 2 will face an undocumented choice: root `[project.dependencies]`, root `[dependency-groups]`, or `api/pyproject.toml` `[project.dependencies]`.
- **Why deferred:** Prompt 3's adversarial review surfaced this. No real dependency lands until Part 2 / Prompt 4+; documenting before the first real case risks getting the worked example wrong.
- **Action when triggered:** Add a "where do dependencies go before each member has a build backend" subsection to ADR 0023 (or to `docs/setup/uv-quickstart.md`) with a worked example, when the first real dependency lands.
- **Target:** When the first real workspace-member dependency is added (likely Prompt 4 or early Part 2).
- **Trail:** Prompt 3 session journal, second-opinion review.

### ADR 0021 maturity-horizon sentence + `required-version` asymmetry
- **Status:** ADR 0021 says uv is "production-stable through 2025–2026" (three years of public evidence) while the open question is "maintainable in 2028 and beyond" (a five-year horizon). The Divergence section concedes pip-tools as the "documented escape hatch" but does not name the trigger conditions for falling back. Separately, the ADR cites the MCP SDK's `[tool.uv] required-version = ">=0.9.5"` declaration as precedent but explicitly chooses not to declare one for SBS, with the rationale "revisit if version drift causes friction."
- **Why deferred:** Prompt 3's adversarial review surfaced this. Wording-only changes; no behavioural fix needed. The ADR is already Accepted.
- **Action when triggered:** Soften "production-stable through 2025–2026" to its evidentiary base; name explicit re-evaluation triggers (e.g., "Astral pricing/licensing change, `[tool.uv]` table shape change, or Part 9 unconditionally"); add a sentence justifying the `required-version` asymmetry with the MCP precedent.
- **Target:** Next harness-cleanup prompt that touches ADRs (or before Part 9 production readiness).
- **Trail:** Prompt 3 session journal, second-opinion review.

### End-of-Part-1 checkpoint discipline
- **Status:** Commitment recorded; checkpoint to be executed between last Part 1 prompt and first Part 2 prompt.
- **What's deferred:** Running the full seven-category audit established before Prompt 3 (repository structural integrity, documentation consistency, harness functional verification, git history sanity, GitHub repo configuration, carry-over fix verification, cross-check against PLAN.md).
- **Why deferred:** End-of-Part-1 is the right cadence; running it mid-Part would be premature and noisy.
- **Action when triggered:** Run all seven audit categories; commit output to `docs/checkpoints/end-of-part-1.md`; do not start Part 2 until checkpoint is committed.
- **Target:** Between Prompt 8 (Part 1 final) and the first Prompt of Part 2.
- **Trail:** This entry; the audit pattern itself was established in PR #20.

### Sprint brief extraction from PLAN.md (Finding 1 + R1)
- **Status:** Cross-review (gpt-5.4) flagged PLAN.md as mixing plan + sprint control + demo narrative.
- **What's deferred:** Extracting the sprint-control prose (audience description, escalation paragraphs, fallback narrative) from PLAN.md's "May 25 sprint kickoff critical path" section into a separate `docs/sprint-briefs/2026-05-25-lima.md`. PLAN.md keeps per-Part scope subsections (durable plan content).
- **Why deferred:** Out of scope for Prompt 4's paper-only scope-lock; rewriting the document structure tonight would expand the diff beyond agreed scope.
- **Action when triggered:** Create `docs/sprint-briefs/` directory; move sprint-control prose; leave a PLAN.md pointer.
- **Target:** Prompt 5 (once tooling lands).
- **Trail:** Cross-review 2026-05-17, Triage Finding 1 + R1.

### Per-Part "May 25 acceptance" checklist items (Finding 2 + R3)
- **Status:** Cross-review flagged the per-Part "May 25 scope" subsections as describing deliverables without "done means" acceptance criteria. "Full / Reduced / Deferred" is not tied to test evidence.
- **What's deferred:** Adding explicit "May 25 acceptance" checklist items in each Part's checklist section, anchored to the per-Part May 25 scope subsection. Each Part needs: live / recorded / static exemplar / architecture-only evidence type, acceptance check, owner, latest cut date.
- **Why deferred:** Each Part owns its own acceptance criteria; landing them as a batch tonight would expand Prompt 4 outside paper-only.
- **Action when triggered:** Each Part's first prompt (Prompts 5-8) adds the "May 25 acceptance" checklist.
- **Target:** Prompts 5-8.
- **Trail:** Cross-review 2026-05-17, Triage Finding 2 + R3.

### DEFERRED.md hygiene pass (Finding 4)
- **Status:** Cross-review flagged that decision gates / exit conditions for deferred work are not consistently stated across this file.
- **What's deferred:** A pass to ensure every active deferral has: a clear trigger condition, a target Part or date, and a documented re-entry criterion. ADR 0025 introduces the Promotion criteria pattern; older entries lack it.
- **Why deferred:** Document-wide hygiene pass is its own task and not in scope for the May 25 scope-lock.
- **Action when triggered:** Walk every entry; add Promotion criteria / re-entry triggers where missing; mark stale entries Resolved.
- **Target:** End of Part 1 (between Prompt 8 and Part 2 start, as part of the existing end-of-Part-1 checkpoint).
- **Trail:** Cross-review 2026-05-17, Triage Finding 4.

### Scripted local bring-up (`scripts/dev-up.sh` or `make dev-up`) (D1)
- **Status:** Cross-review reviewer would not accept "Part 9 fully deferred" without a minimum reproducibility bar for the May 25 demo. The ADR addresses this by naming May 25 as a deliberate, time-bounded exception to the one-command-deploy north-star.
- **What's deferred:** A one-command local bring-up — `scripts/dev-up.sh` or `make dev-up` — that brings up Homebrew Postgres + Redis + a venv-installed FastAPI process. Compensating control while Helm/Terraform are deferred.
- **Why deferred:** Adding this tonight expands Prompt 4 from paper-only into infra scaffolding work; it is the right Part-5-or-6 deliverable.
- **Action when triggered:** Write the script, document required Homebrew formulae, smoke-test on the maintainer's machine, link from ADR 0025 Consequences.
- **Target:** Prompt 5 or 6.
- **Trail:** Cross-review 2026-05-17, Triage D1.

### PLAN.md "13-prompt sequence" needs date column (R6)
- **Status:** Cross-review flagged that the prompt sequence in PLAN.md is written as if prompts are near-linear and bounded, hiding cross-prompt rework and calendar pressure.
- **What's deferred:** A one-column "date landed / target date" alongside each prompt in the 13-prompt sequence list, so a future reader sees both the count and the calendar pressure.
- **Why deferred:** Readability improvement, not a contradiction; out of paper-only scope tonight.
- **Action when triggered:** Add a date column to the prompt list during a PLAN.md hygiene pass.
- **Target:** Prompt 5 or as part of any PLAN.md restructure.
- **Trail:** Cross-review 2026-05-17, Triage R6.

### Zscaler CA bundle path mismatch with setup doc
- **Status:** Surfaced during Prompt 4 closeout when `scripts/cross_review.py` failed with `CERTIFICATE_VERIFY_FAILED`.
- **What's deferred:** Updating `docs/setup/corporate-proxy-and-zscaler.md` to reflect what actually works on the maintainer's machine.
- **What was observed:** (a) The conventional `~/certs/wbg-ca-bundle.pem` path the setup doc references does not exist on the maintainer's machine. (b) The WBG CAs are installed in the macOS System keychain (`security find-certificate -a /Library/Keychains/System.keychain` shows "WBG Issuing CA1 G2", "...CA2 G2", "...CA6 G2", "...CA7 G2" plus "World Bank Group JSS Built-in Certificate Authority"). (c) The openai SDK uses `httpx`, which honours `SSL_CERT_FILE` but does NOT consult the macOS System keychain by default. (d) Working path: export the keychain certs (`security find-certificate -a -p /Library/Keychains/System.keychain > /tmp/keychain.pem`), concatenate with certifi's bundle (`cat $(python -c 'import certifi;print(certifi.where())') /tmp/keychain.pem > combined.pem`), and set `SSL_CERT_FILE=combined.pem REQUESTS_CA_BUNDLE=combined.pem`.
- **Why deferred:** Out of scope for Prompt 4 (paper-only scope-lock).
- **Action when triggered:** Update `docs/setup/corporate-proxy-and-zscaler.md` to document the macOS keychain path explicitly, with a recipe for combining keychain + certifi bundles. Consider also adding a helper script `scripts/build-ca-bundle.sh` that produces the combined bundle.
- **Target:** Next time the setup doc is touched.
- **Trail:** Prompt 4 session journal.

### Sprint-phasing comparator research note (ADR 0025 promotion blocker)
- **Status:** ADR 0025 is Proposed pending a sprint-phasing or minimum-credible-demo comparator in `docs/research/`.
- **What's deferred:** A research note added to `docs/research/market-comparators.md` (or a sibling file) that documents at least one externally-verifiable precedent for how supervisory authorities or comparable institutions stage a short-horizon kickoff demonstration. Candidates worth checking: FCA Regulatory Sandbox cohort phasing, BIS Innovation Hub project staging, Cambridge SupTech Lab post-mortems, GDS / 18F sprint-zero patterns, World Bank / CGAP SupTech project sequencing notes.
- **Why deferred:** Prompt 4's job was to lock May 25 scope. Producing the research note in the same prompt would have either delayed the scope-lock or fabricated a precedent. The honest move is to land the scope-lock as Proposed and own the research-note gap.
- **Action when triggered:** Open a follow-up prompt scoped to the research note alone. Add the section to `docs/research/`. Update ADR 0025 Precedent to cite it. Flip ADR 0025 status to Accepted in `docs/adr/README.md` and in the ADR itself. Update [docs/DECISIONS.md](DECISIONS.md) with a one-line note that ADR 0025 was promoted.
- **Target:** Before May 25 (so the scope-lock decision is fully grounded by sprint kickoff). Must land off the critical path (i.e., interleaved between or after Prompts 5-8, not inside them) — Prompts 5-8 are the signed-ingestion stack and displacing one of them directly increases the schedule risk that ADR 0025 Consequences names as "real."
- **Trail:** ADR 0025 Promotion criteria, Prompt 4 session journal, [docs/reviews/2026-05-17-may-25-critical-path-restructure.md](reviews/2026-05-17-may-25-critical-path-restructure.md) (benchmark-checker finding).

### Prompt 7 closeout — Day-2 review-disposition deferrals

- **Status:** Surfaced by the H subagents and the cross-review on 2026-05-19.
  Fix-now items landed in commits on this branch; the items below are
  named explicitly so the next Part-3-touching prompt can pick them up.
- **What's deferred:**
  - **RFC 8705 base64url thumbprint encoding.** The implementation uses
    lowercase hex on both sides. The sandbox is internally consistent
    but SDKs that follow RFC 8705 verbatim will not interoperate. Migrate
    alongside the HS256→RS256 transition in Part 9. ADR 0031
    §Consequences names the gap.
  - **JWT `kid` resolver.** The token header carries `kid=sandbox-v1`
    from issuance day one, but `verify_token` ignores `kid` and uses a
    single configured key. Rotation today therefore requires synchronous
    cutover. Add a `kid → key` resolver with a previous-kid grace
    window; update ADR 0032 to amend the claimed rotation mechanism.
  - **Rate-limit Lua script clock source.** The script uses Python's
    `time.time()` (sent via `ARGV[1]`) rather than Redis's `TIME`
    command. Multi-replica NTP drift can produce apparent-refill spikes;
    swap to `redis.call("TIME")` in Part 9 when the Helm chart adds
    multi-replica.
  - **Test-fixture blanket override blind spot.** `tests/conftest.py`
    bypasses mTLS, OAuth, HMAC, and rate-limit dependencies on every
    test app. A future route that forgets to declare the OAuth dep
    would pass tests. Add a conformance test that introspects every v1
    route's `dependant` to assert OAuth scope dep presence on protected
    routes.
  - **JWS signing-key secret-hygiene.** `dev-ca/oauth-signing-key.bin`
    and `dev-ca/cursor-signing-key.bin` are sandbox-only but the README
    "one-command deploy" leaves them on disk. Add a `dev-ca/.gitignore`
    with `*` and a "If you leaked a sandbox secret" subsection to
    SECURITY.md before any external vendor onboards.
  - **Audit-log subsystem proper.** Workstream F's auth-failure
    `_logger.warning("auth_failure", ...)` is the minimum-viable
    observability hook. Part 6 lands the durable audit-log table that
    queries against the same event family.
  - **OpenAPI spec match-test on scopes / new tables.** The match test
    does not yet cover the `oauth_clients`, `institution_certificates`,
    `institution_secrets` operator-side tables, nor the scope set in
    `securitySchemes`. Extend `test_openapi_pydantic_match.py` (or
    a sibling test) in Part 7 alongside the developer-portal cut.
  - **`disable_mtls_for_tests` environment guard.** Settings should
    refuse to instantiate when `disable_mtls_for_tests=true` AND
    `environment in {"staging","prod"}` to prevent an accidental env
    var from granting ambient admin in non-dev overlays.
  - **`oauth_clients.cert_thumbprint_required` not populated.** Demo
    seed leaves it NULL; the per-client cert-binding check at the token
    endpoint is therefore a no-op for the demo clients (the JWT-level
    `cnf.x5t#S256` still binds at verify time). Populate in Part 8
    admin-API onboarding flow.
- **Why deferred:** Each is a follow-on engineering item, not a May 25
  demo blocker; the auth chain in this branch is correct end-to-end
  (320 tests pass) and the demo claim "every request is mTLS-authenticated,
  HMAC-signed, OAuth-authorised, rate-limited" is verifiable via
  `bash scripts/smoke-test-auth.sh`.
- **Action when triggered:** Each item has a named home (Part 6, Part 7,
  Part 8, or Part 9) above.
- **Target:** Day-2 prompt opening Part 6 (audit log) is the natural
  vehicle for the audit-trail items; cert-binding seed lands with Part 8
  admin-API work; the rest cluster around Part 9 production readiness.
- **Trail:** docs/reviews/2026-05-19-docs-adr-003-123.md (cross-review),
  /tmp/prompt-07-status.md, the H subagent reports (six in total,
  embedded in the session journal).

### Pressure-test findings deferred to Day 2 amendment pass

- **Status:** Surfaced during the Prompt 7 pre-workstream-A pressure-test review. Five findings are real but out of scope for tonight's auth-chain landing.
- **What's deferred:**
  - **Audit logging of auth events.** Failed mTLS handshakes, expired tokens, replayed signatures, and scope-insufficient rejections should land in the audit log. Deferred because the audit-log subsystem itself is a Part 6 deliverable; auth events feed it when it lands.
  - **GET request body rejection.** A GET with a body is RFC 9110 §9.3.1 undefined-behavior; the API should explicitly 400 such requests. This is a code-level guard, not an ADR-level decision, and lands in a Day-2 hardening pass.
  - **HMAC secret rotation operational endpoints.** ADR 0027's amendment names the `active_secret`/`previous_secret` rotation grace but the admin endpoints that actually rotate (POST a new secret, retire an old one) are a Part 8 admin-API concern.
  - **OpenAPI route authentication decision.** `GET /v1/openapi.yaml` currently is unauthenticated (the published contract). Whether to gate it behind mTLS-only (no OAuth) is a separate decision; defer until SBS confirms public-vs-partner visibility for the contract document.
  - **Response signing.** Outbound webhook callbacks (Prompt 12) will need outbound HMAC. The contract is unchanged from the inbound shape; landing the outbound primitive is a Prompt 12 concern, not Prompt 7.
- **Why deferred:** Each finding either has a named future home (Part 6 audit log, Part 8 admin work, Prompt 12 webhooks) or is a code-level guard that does not belong in an ADR.
- **Action when triggered:** Each item lands in its named home; no shared trigger.
- **Target:** Day 2 of Prompt 7 (GET-body guard), Part 6 (audit), Part 8 (rotation endpoints), Prompt 12 (response signing), separate decision needed (OpenAPI auth).
- **Trail:** Prompt 7 pressure-test, [/tmp/prompt-07-pressure-test-fixes.md](file:///tmp/prompt-07-pressure-test-fixes.md) (operator-local).

## How to revisit

At the start of Part 9, the planner reads this document top-to-bottom and produces a Part 9 work plan. Items resolved in earlier Parts should be moved to the "Resolved" section below with a one-line note pointing at the resolving PR/commit.

## Resolved

### Real `.secrets.baseline` generation
- **Resolved by:** PR #16, commit `54b7542` (`chore: generate real .secrets.baseline (closes promise from ADR 0016)`).
- **What landed:** Real `detect-secrets` baseline generated against the working tree; the stub is gone.
- **Trail:** ADR 0016, Prompt 2 session journal, PR #16.

### Subagent-verdict table in session-journal template
- **Resolved by:** Prompt 3 (this PR).
- **What landed:** The empty markdown table in `docs/sessions/_template.md` has been replaced with an inline `## Subagent verdicts` heading and a short instruction that the operator writes one line per subagent at closeout. Two prompts of evidence (both with empty tables) did not justify the plumbing for auto-population; revisit if subagent run volume grows.
- **Trail:** Prompt 2 retrospective, Prompt 3 session journal.

## 2026-05-19 — Runtime fix addendum deferrals

### uvicorn internals fragility (Part 9)
`api/sbs_api/middleware/mtls_transport.py` reaches into uvicorn-private
state by walking asyncio task frames to find `RequestResponseCycle`.
This is the bridge until uvicorn ships the ASGI TLS extension or we
migrate to hypercorn. Part 9 deliverable: pick one path and remove the
frame-walking middleware.

### PR squash-merge style (Day-2 conversation with a second reviewer)
PR #33 squash-merged 13 commits of Prompt 7 work and lost ~3,700 lines
during the squash conflict resolution. Switch the repo's default merge
style for large multi-file PRs from squash to merge-commit or
rebase-merge. Squash works for small fix-it PRs; it does not scale to
architectural multi-workstream deliveries that span 12+ days.

## From Prompt 9 close (2026-05-21)

- Spectral lint crashes with "Cannot read 'enum' of null" across versions 6.11.1, 6.13.0, 6.14.2. Pydantic-OpenAPI match test covers the load-bearing case; Spectral is currently `continue-on-error: true` in standards-pack-validate.yml. Diagnose by bisecting either spec paths or .spectral.yaml rules.
- `uv pip install -e ./api` fails in CI because `api/pyproject.toml` doesn't configure setuptools package discovery (four top-level dirs: openapi, sbs_api, devportal, migrations). CI uses `uv run --with <pkg>` workaround. Proper fix: add `[tool.setuptools.packages.find]` with explicit include/exclude, or migrate to src-layout.
- All `npx --yes <package>` calls in workflows should pin versions (currently only Spectral is pinned).
- Cross-day determinism in synthetic corpus generator: CSV bytes change across UTC date boundaries because `received_date` is wall-clock. Add `--window-start` / `--window-end` flags so demo.sh runs are byte-identical across days.
- Browser-render check via Playwright (exit gate (f) for portal route is currently manual).
- ADR 0023 workspace layout: revisit sdk-helpers/ inclusion as a workspace member.

## From Prompt 10 / WS1 (2026-05-22)

- **Sprint retro note — fabricated comparators in ## Precedent.** During the WS1 ADR draft I cited "OPRM (Open Regulator Project on Risk Markings)" and "OECD's supervisory-data style guide" as severity-token comparators in market-comparators.md §5.A.V. Neither is a publicly-verifiable named reference. Caught on re-read before the commit landed; replaced with IBM Carbon (Notification / Tag kinds), USWDS Alert variants, Salesforce Lightning notification themes — all real and publicly documented. The benchmark-checker rule is *specificity of section and comparator*; fabricated comparators undermine the gate by appearing to satisfy it while actually carrying no precedent weight. Going forward: every named comparator in a ## Precedent section must be either (a) directly URL-cited or (b) something the author has read recent first-hand documentation of. Names like "X Standards Body" without a URL are the failure mode. The `benchmark-checker` subagent does not currently verify URL reachability or that the named standard exists — that's the gap this entry names.
- **Action when triggered:** if benchmark-checker is upgraded to validate comparator existence (URL HEAD check + spot-check against the linked page's title), this entry can be marked Resolved. Until then, the safeguard is reviewer attention to specifically-named bodies in the ## Precedent section of any new ADR.
- **Trail:** ADR 0041 second draft (before commit), market-comparators.md §5.A.V revision.
