#!/usr/bin/env python3
"""Closeout pipeline for a prompt. Runs subagent reviews (stub hooks for now),
cross-review, an adversarial pass, an optional fresh-machine deploy test, then
PAUSES for a typed approval before doing any git operations.

The subagent steps are stubbed: this script prints what would run and leaves
the actual subagent invocation to the Claude session that runs /close-prompt.
The git-side steps (commit, branch, push, PR) are fully implemented.

The typed approval gate is non-bypassable. There is no -y flag. If stdin is
not a TTY the script exits non-zero rather than auto-approving.

Cross-review behaviour:
    - If all four AZURE_OPENAI_* env vars are set and no skip flag is given,
      scripts/cross_review.py runs against the staged diff. A non-zero exit
      hard-fails the closeout (carry-over fix #1a from Prompt 1: previously
      the script swallowed the failure and committed anyway).
    - On success, the produced docs/reviews/<date>-staged-diff.md file is
      asserted to exist and be non-empty, then `git add`-ed so it lands in
      the same commit as the change it documents (carry-over fix #1b).
    - The only sanctioned bypass is --skip-cross-review-with-reason "<reason>".
      The reason is required, non-empty, and written into the session journal.
      The older --no-cross-review flag is removed; use the with-reason form.

Deploy-test trigger (carry-over fix #2):
    Paths are matched as anchored regexes, not substrings, so generic script
    names like scripts/setup_hooks.sh do not falsely trigger the warning.

Usage:
    python scripts/close_prompt.py --prompt 3 --part 1
                                   --slug uv-project-and-python-tooling
                                   [--dry-run]
                                   [--skip-cross-review-with-reason "<reason>"]

--prompt N is required (Prompt-3 carry-over fix #1). The journal filename
uses the prompt number directly; the prior regex-from-slug heuristic mis-
named Prompt 2's journal as `prompt-01-...` and was renamed in PR #17 after
the fact. No fallback is allowed — explicit is the only path.

Triage-line gate (Prompt-3 carry-over fix #3): after `run_cross_review`
returns successfully, the closeout reads the cross-review file and refuses
the typed-approval gate if the literal `_TODO: human-filled` substring is
still present in the file's `## Triage` section. The operator must fill in
the disposition (accept / defer / reject + reason) for each finding before
typing `approve`.

Cross-review filename stability (Prompt-3 carry-over fix #4): the slug
threaded into cross_review.py via `--slug` is the branch's prompt slug, so
same-day re-runs land at distinct filenames per prompt rather than all
overwriting `<date>-staged-diff.md`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import re
import subprocess
import sys
import textwrap

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEWS_DIR = REPO_ROOT / "docs" / "reviews"
SESSIONS_DIR = REPO_ROOT / "docs" / "sessions"
PR_TEMPLATE = REPO_ROOT / ".github" / "pull_request_template.md"

APPROVAL_STRINGS = {"approve", "APPROVE"}

# Deploy-test trigger. Each regex is anchored to the start of the staged path
# (paths returned by `git diff --staged --name-only` have no leading slash).
#
# These patterns MUST match real infrastructure paths and MUST NOT match
# generic harness scripts. The Prompt 1 bug was an over-broad substring match
# on "scripts/setup_" which matched scripts/setup_hooks.sh (a no-op for deploy).
#
# Inventory of intent:
#   ^infra/         — k8s manifests, kustomize overlays, network policy
#   ^helm/          — Helm chart sources and values files
#   ^terraform/     — Terraform modules (bare-metal + Azure)
#   ^docker/        — Dockerfiles organised under docker/<service>/
#   ^Dockerfile$    — a Dockerfile at repo root (single-image projects)
#   ^compose...     — docker-compose.yml or compose.yaml at repo root
DEPLOY_TOUCH_REGEXES = (
    re.compile(r"^infra/"),
    re.compile(r"^helm/"),
    re.compile(r"^terraform/"),
    re.compile(r"^docker/"),
    re.compile(r"^Dockerfile$"),
    re.compile(r"^compose[^/]*\.ya?ml$"),
    re.compile(r"^docker-compose[^/]*\.ya?ml$"),
)


def load_dotenv_if_present() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, **kwargs)


def git_staged_files() -> list[str]:
    r = run(["git", "diff", "--staged", "--name-only"])
    return [line for line in r.stdout.splitlines() if line.strip()]


def git_current_branch() -> str:
    r = run(["git", "branch", "--show-current"])
    return r.stdout.strip()


def infer_part_number() -> int:
    plan = REPO_ROOT / "docs" / "PLAN.md"
    if not plan.exists():
        return 1
    text = plan.read_text(encoding="utf-8")
    matches = re.findall(r"^### Part (\d+)", text, re.MULTILINE)
    parts = [int(m) for m in matches]
    return min(parts) if parts else 1


def infer_slug_from_branch(branch: str, default: str) -> str:
    m = re.match(r"part-(\d+)/(.+)", branch)
    if m:
        return m.group(2)
    return default


def deploy_touched(files: list[str]) -> bool:
    """True if any staged path matches an infra/deploy regex.

    Substring matching was removed because it produced false positives on
    paths like scripts/setup_hooks.sh. See DEPLOY_TOUCH_REGEXES above.
    """
    return any(any(rx.match(f) for rx in DEPLOY_TOUCH_REGEXES) for f in files)


def generate_commit_message(files: list[str], slug: str) -> str:
    docs_only = all(f.startswith("docs/") or f in ("README.md", "CLAUDE.md") for f in files)
    workflow_only = all(
        f.startswith(".claude/") or f.startswith(".github/") or f.startswith("scripts/")
        for f in files
    )
    if docs_only:
        ctype = "docs"
    elif workflow_only:
        ctype = "chore"
    else:
        ctype = "feat"
    subject = slug.replace("-", " ")
    body = "Files:\n" + "\n".join(f"- {f}" for f in files[:30])
    if len(files) > 30:
        body += f"\n- ... and {len(files) - 30} more"
    return f"{ctype}: {subject}\n\n{body}\n"


def generate_pr_body(
    part: int,
    slug: str,
    session_journal: pathlib.Path,
    cross_review_path: pathlib.Path | None,
) -> str:
    template_text = ""
    if PR_TEMPLATE.exists():
        template_text = PR_TEMPLATE.read_text(encoding="utf-8")

    journal_rel = session_journal.relative_to(REPO_ROOT) if session_journal.exists() else None
    cross_rel = cross_review_path.relative_to(REPO_ROOT) if cross_review_path else None

    addendum = textwrap.dedent(
        f"""

        ---

        ## Closeout artifacts

        - **Session journal:** `{journal_rel}`
        - **Cross-model review:** {f"`{cross_rel}`" if cross_rel else "_not run_"}
        - **Active Part:** {part}
        - **Slug:** `{slug}`
        """
    )
    return template_text + addendum


def write_session_journal(
    slug: str,
    part: int,
    prompt: int,
    cross_review_path: pathlib.Path | None,
    cross_review_skip_reason: str | None,
    adversarial_summary: str,
    files: list[str],
) -> pathlib.Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    date = dt.date.today().isoformat()
    journal_name = f"{date}-prompt-{prompt:02d}-{slug.replace('/', '-')}.md"
    path = SESSIONS_DIR / journal_name

    if cross_review_path:
        try:
            cr_display = cross_review_path.relative_to(REPO_ROOT)
        except ValueError:
            cr_display = cross_review_path
        triage_block = (
            f"Cross-model review ran. See `{cr_display}`.\n"
            "Triage line: _human-filled — disposition each finding as "
            "accept / defer / reject._"
        )
    elif cross_review_skip_reason:
        triage_block = f"SKIPPED: {cross_review_skip_reason}"
    else:
        triage_block = "_Not run._"

    # Build flush-left explicitly. textwrap.dedent is unreliable here because
    # the embedded join over `files` produces lines whose indent differs from
    # the surrounding template, which defeats dedent's common-whitespace
    # calculation. Regression: see tests/test_close_prompt.py
    # test_journal_no_six_space_indent_anywhere.
    file_lines = [f"  - {f}" for f in files[:60]]
    if len(files) > 60:
        file_lines.append("  - ... and more")

    # The `## Subagent verdicts` heading + boilerplate that used to live here
    # was removed in Prompt 3 (carry-over fix #5). Subagent verdicts now go
    # inline in the journal's template-driven section, written by the operator
    # at closeout. The structured top is metadata + cross-review + adversarial.
    parts: list[str] = [
        f"# Session journal — {date} — {slug}",
        "",
        f"- **Date:** {date}",
        f"- **Prompt:** {prompt}",
        f"- **Part:** {part}",
        f"- **Slug:** {slug}",
        f"- **Files touched ({len(files)}):**",
        *file_lines,
        "",
        "## Cross-model review — triage line",
        "",
        triage_block,
        "",
        "## Adversarial review",
        "",
        adversarial_summary or "_See inline report during /close-prompt run._",
        "",
        "## What landed",
        "",
        "_Operator fills in: one paragraph, plain language, readable by Veronica._",
        "",
        "## Decisions locked",
        "",
        "_Operator fills in: one line per decision, with the ADR if any._",
        "",
        "## Decisions deferred (to a named future prompt / part)",
        "",
        "_Operator fills in: one line per deferral, with target prompt or Part._",
        "",
        "## Decisions flagged for cross-model review",
        "",
        "_Operator fills in: one line per flag, naming the model and owner._",
        "",
        "## Subagent verdicts",
        "",
        "_Operator fills in: one line per subagent run on the staged diff. "
        "Format: `<subagent>: <verdict> — <headline finding>`._",
        "",
        "## Paste-ready block for the maintainer",
        "",
        "> Prompt N closed. Branch: `part-NN/<slug>`. PR: <url>. "
        "Locked: <one line>. Deferred: <one line>. "
        "Flagged for cross-review: <one line>. Active Part: <N>. "
        "Next prompt opens with: <pointer>.",
        "",
        "## Notes",
        "",
        "_Operator fills in: anything that doesn't fit above. Keep brief._",
        "",
    ]
    summary = "\n".join(parts) + "\n"
    path.write_text(summary, encoding="utf-8")
    return path


def prompt_typed_approval(summary_text: str) -> bool:
    print()
    print("=" * 72)
    print("CLOSEOUT SUMMARY")
    print("=" * 72)
    print(summary_text)
    print("=" * 72)
    print()
    print("Type 'approve' to commit, push, and open a PR.")
    print("Anything else aborts.")
    if not sys.stdin.isatty():
        print("[non-interactive stdin detected — aborting]")
        return False
    try:
        answer = input("approval> ").strip()
    except (EOFError, KeyboardInterrupt):
        print("[aborted]")
        return False
    return answer in APPROVAL_STRINGS


def ensure_branch(slug: str, part: int) -> str:
    branch = git_current_branch()
    target = f"part-{part:02d}/{slug.split('/')[-1]}"
    if branch == "main" or branch == "":
        r = run(["git", "checkout", "-b", target])
        if r.returncode != 0:
            raise RuntimeError(f"git checkout -b failed:\n{r.stderr}")
        return target
    return branch


def commit_staged(message: str) -> None:
    gitsign_configured = bool(run(["git", "config", "--get", "gpg.x509.program"]).stdout.strip())
    sign_flag = ["-S"] if gitsign_configured else []
    if not gitsign_configured:
        print("[warn] gitsign not configured; committing unsigned. Part 2 finalizes signing.")
    r = run(["git", "commit", *sign_flag, "-m", message])
    if r.returncode != 0:
        raise RuntimeError(f"git commit failed:\n{r.stdout}\n{r.stderr}")
    print(r.stdout)


def push_branch(branch: str) -> None:
    r = run(["git", "push", "-u", "origin", branch])
    if r.returncode != 0:
        raise RuntimeError(f"git push failed:\n{r.stdout}\n{r.stderr}")
    print(r.stdout)


def open_pr(title: str, body: str) -> str:
    r = run(["gh", "pr", "create", "--title", title, "--body", body, "--base", "main"])
    if r.returncode != 0:
        raise RuntimeError(f"gh pr create failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout.strip()


AZURE_ENV_VARS = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)

# Literal substring written by cross_review.py's enforce_sections() into the
# `## Triage` section when the cross-review file lands. The operator must
# overwrite this with `accept` / `defer` / `reject` + reason before approving.
TRIAGE_TODO_MARKER = "_TODO: human-filled"


def _extract_last_triage_section(body: str) -> str | None:
    """Return the body of the last `## Triage` h2 section, slice spanning from
    the heading to the next `## ` heading (or EOF), or None if no `## Triage`
    heading exists.

    The "last" rule handles hand-edited files with duplicated headings — the
    operator's most recent state is what gates approval.

    Headings are matched on `## Triage` at line start; `### Triage` (h3) does
    not match. Section termination is any subsequent line starting with `## ` —
    the cross-review file format is one `# H1` followed by `## H2` sections,
    so anchoring to `## ` is sufficient and avoids over-matching on `###`.
    """
    lines = body.splitlines(keepends=True)
    triage_starts = [
        i for i, line in enumerate(lines) if line.startswith("## Triage")
    ]
    if not triage_starts:
        return None
    start = triage_starts[-1]
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "".join(lines[start:end])


def check_triage_filled(review_path: pathlib.Path) -> None:
    """Raise RuntimeError if the cross-review file's `## Triage` section still
    contains the placeholder marker. The closeout cannot proceed until the
    operator dispositions each finding.

    Prompt-3 carry-over fix #3. The Prompt 2 retrospective noted that the
    placeholder was being committed unchanged, defeating the audit-trail
    purpose of the triage line.

    Section-anchored (post-Prompt-3 adversarial review). The earlier whole-file
    substring check was the same brittle-stringy pattern the slug-regex fix was
    retiring: any cross-review that quoted the marker in `## Summary` or
    `## Disagreements` (a self-aware meta-review of the gating logic, for
    example) would permanently jam the gate. The check now slices the file to
    the last `## Triage` section and scans only inside it.
    """
    if not review_path.exists():
        raise RuntimeError(
            f"Triage-line gate: expected cross-review file is missing: {review_path}."
        )
    body = review_path.read_text(encoding="utf-8")
    try:
        display = review_path.relative_to(REPO_ROOT)
    except ValueError:
        display = review_path

    triage_slice = _extract_last_triage_section(body)
    if triage_slice is None:
        raise RuntimeError(
            f"Triage-line gate: {display} has no `## Triage` section. "
            "scripts/cross_review.py:enforce_sections should have written one; "
            "the file is malformed. Re-run the cross-review or repair the file "
            "by hand before retrying /close-prompt."
        )
    if TRIAGE_TODO_MARKER in triage_slice:
        raise RuntimeError(
            f"Triage-line gate: {display} still contains the placeholder "
            f"`{TRIAGE_TODO_MARKER}` in its `## Triage` section.\n"
            "Open the file and disposition each finding as `accept` / `defer` "
            "/ `reject` with a one-line reason, then re-run /close-prompt."
        )


def run_cross_review(
    skip_reason: str | None,
    slug: str | None = None,
) -> tuple[pathlib.Path | None, str | None]:
    """Return (review_file_path, skip_reason).

    Hard-fails (raises RuntimeError) if cross_review.py is invoked and exits
    non-zero, or if it returns 0 but the expected output file is missing or
    empty. Closeout artifacts that prove the closeout happened must be in the
    same commit as the change they document.

    If skip_reason is provided, cross-review is skipped and the reason is
    propagated to the session journal. The reason must be non-empty — argparse
    enforces presence; we re-check for whitespace-only strings here.

    If skip_reason is None and one of the four AZURE_OPENAI_* env vars is
    missing, we fail and instruct the operator to either fix the env or pass
    --skip-cross-review-with-reason. We deliberately do NOT silently skip.

    `slug`, when provided, is threaded into cross_review.py via `--slug` so
    the output filename reflects the current prompt rather than the generic
    `staged-diff` (Prompt-3 carry-over fix #4).
    """
    if skip_reason is not None:
        if not skip_reason.strip():
            raise RuntimeError(
                "--skip-cross-review-with-reason requires a non-empty reason. "
                "Example: --skip-cross-review-with-reason 'VPN off, no Azure access'."
            )
        print(f"[cross-review] skipped: {skip_reason}")
        return None, skip_reason

    missing = [v for v in AZURE_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            "Cross-review cannot run — missing env vars: "
            f"{', '.join(missing)}.\n"
            "Either set them (see .env.example) or pass "
            "--skip-cross-review-with-reason '<reason>'."
        )

    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "cross_review.py"),
           "--target", "staged"]
    if slug:
        cmd.extend(["--slug", slug])
    print(f"[cross-review] calling {' '.join(cmd[1:])}")
    r = run(cmd)
    if r.returncode != 0:
        # carry-over fix #1a: a non-zero exit must hard-fail. Prompt 1
        # silently tolerated this and committed anyway.
        raise RuntimeError(
            "Cross-review failed. The closeout cannot proceed.\n"
            f"stdout:\n{r.stdout}\n"
            f"stderr:\n{r.stderr}\n"
            "If this is a transient Azure / network issue, retry. "
            "If you must close without the review, re-run with "
            "--skip-cross-review-with-reason '<reason>'."
        )

    out_lines = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    if not out_lines:
        raise RuntimeError(
            "Cross-review exited 0 but produced no output path on stdout. "
            "Check scripts/cross_review.py."
        )
    review_path = pathlib.Path(out_lines[-1])
    if not review_path.is_absolute():
        review_path = REPO_ROOT / review_path

    # carry-over fix #1b: the review file is written AFTER the initial staging
    # snapshot, so we assert it exists and `git add` it before commit. This
    # guarantees the audit trail is one commit deep — the change and its
    # cross-review proof land together. Do not move this file elsewhere.
    if not review_path.exists():
        raise RuntimeError(
            f"Cross-review exited 0 but expected file is missing: {review_path}.\n"
            "scripts/cross_review.py contract is to print the written path on "
            "the last stdout line. Investigate that script before retrying."
        )
    if review_path.stat().st_size == 0:
        raise RuntimeError(
            f"Cross-review wrote an empty file: {review_path}. Investigate."
        )
    add = run(["git", "add", str(review_path)])
    if add.returncode != 0:
        raise RuntimeError(f"git add of cross-review file failed:\n{add.stderr}")
    try:
        display = review_path.relative_to(REPO_ROOT)
    except ValueError:
        display = review_path
    print(f"[cross-review] wrote and staged {display}")
    return review_path, None


def main() -> int:
    load_dotenv_if_present()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-cross-review-with-reason",
        dest="skip_cross_review_with_reason",
        default=None,
        help=(
            "Skip the cross-model review step. The reason is required, "
            "non-empty, and written into the session journal. Appropriate "
            "uses: VPN off, deliberate Azure-credential gap, scheduled "
            "outage. Not appropriate: 'the review came back ugly'."
        ),
    )
    parser.add_argument("--slug", default=None)
    parser.add_argument("--part", type=int, default=None)
    parser.add_argument(
        "--prompt",
        type=int,
        required=True,
        help=(
            "Prompt number (required). Used directly in the session-journal "
            "filename. Prompt-3 carry-over fix #1: removes the prior "
            "regex-from-slug heuristic that mis-named Prompt 2's journal as "
            "`prompt-01-...`."
        ),
    )
    args = parser.parse_args()

    files = git_staged_files()
    if not files:
        sys.exit("No staged changes. Stage what you mean to commit and try again.")

    part = args.part or infer_part_number()
    branch_now = git_current_branch()
    slug = args.slug or infer_slug_from_branch(branch_now, default="workflow-harness")
    prompt = args.prompt

    print(f"[prompt] {prompt}")
    print(f"[part] {part}")
    print(f"[branch] {branch_now or '(detached)'}")
    print(f"[slug] {slug}")
    print(f"[files staged] {len(files)}")

    # Step 2 — subagent reviews are run by the Claude session that invokes
    # /close-prompt; verdicts are recorded inline in the journal's template-
    # driven `## Subagent verdicts` section by the operator at closeout.
    print("\n[subagents] Run reviewer, architect-guard, doc-sync, "
          "regulator-readability, benchmark-checker, second-opinion via the "
          "Claude session. Block on any BLOCK verdict.")

    # Step 3 — cross-model review (hard-fail on error; staged on success).
    cross_review_path, cross_review_skip_reason = run_cross_review(
        args.skip_cross_review_with_reason,
        slug=slug,
    )

    # Step 3b — triage-line gate. The cross-review file's `## Triage` section
    # ships with a placeholder `_TODO: human-filled` that the operator must
    # replace with `accept` / `defer` / `reject` + reason for each finding.
    # Prompt-3 carry-over fix #3.
    if cross_review_path is not None:
        check_triage_filled(cross_review_path)

    # Step 4 — adversarial review (stubbed for the Claude session).
    adversarial_summary = (
        "Adversarial pass is run by the Claude session via the second-opinion "
        "subagent."
    )
    print("[adversarial] Run second-opinion subagent on staged diff.")

    # Step 5 — fresh-machine deploy test.
    if deploy_touched(files):
        print("\n[deploy-test] Staged files touch infra/helm/terraform/docker. "
              "Run `bash scripts/fresh_machine_test.sh` on a clean environment "
              "and report pass/fail before approving.")
    else:
        print("[deploy-test] not applicable for this diff.")

    # Step 6 — summary + typed approval.
    commit_msg = generate_commit_message(files, slug)
    target_branch = f"part-{part:02d}/{slug.split('/')[-1]}"
    title = commit_msg.splitlines()[0]
    pr_body_preview = generate_pr_body(
        part=part,
        slug=slug,
        session_journal=SESSIONS_DIR / "(to be written)",
        cross_review_path=cross_review_path,
    )

    summary_text = textwrap.dedent(
        f"""
        Files staged ({len(files)}):
        {chr(10).join('  - ' + f for f in files[:40])}
        {'  - ... and more' if len(files) > 40 else ''}

        Draft branch:  {target_branch}
        Draft commit:  {title}
        Cross-review:  {cross_review_path if cross_review_path else 'SKIPPED: ' + (cross_review_skip_reason or 'not run')}

        --- PR body preview ---
        {pr_body_preview[:1200]}{'...' if len(pr_body_preview) > 1200 else ''}
        """
    ).strip()

    if args.dry_run:
        print("\n[dry-run] would prompt for approval and then commit/push/PR. "
              "Exiting without git operations.")
        print()
        print(summary_text)
        return 0

    if not prompt_typed_approval(summary_text):
        print("\n[abort] approval not given. No git operations performed.")
        return 1

    # Step 7 — write session journal.
    journal = write_session_journal(
        slug=slug,
        part=part,
        prompt=prompt,
        cross_review_path=cross_review_path,
        cross_review_skip_reason=cross_review_skip_reason,
        adversarial_summary=adversarial_summary,
        files=files,
    )
    print(f"[journal] wrote {journal.relative_to(REPO_ROOT)}")
    run(["git", "add", str(journal)])

    # Step 8 — branch, commit, push.
    branch = ensure_branch(slug, part)
    print(f"[branch] on {branch}")
    commit_staged(commit_msg)
    push_branch(branch)

    # Step 9 — open PR.
    pr_body = generate_pr_body(
        part=part,
        slug=slug,
        session_journal=journal,
        cross_review_path=cross_review_path,
    )
    pr_url = open_pr(title=title, body=pr_body)
    print(f"\n[pr] {pr_url}")
    print("\nMain is protected. Do NOT auto-merge. Wait for CI, review the PR, "
          "merge manually via the GitHub UI.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"[error] {e}", file=sys.stderr)
        raise SystemExit(2)
