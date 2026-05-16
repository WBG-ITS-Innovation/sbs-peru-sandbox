#!/usr/bin/env python3
"""Closeout pipeline for a prompt. Runs subagent reviews (stub hooks for now),
cross-review, an adversarial pass, an optional fresh-machine deploy test, then
PAUSES for a typed approval before doing any git operations.

The subagent steps are stubbed: this script prints what would run and leaves
the actual subagent invocation to the Claude session that runs /close-prompt.
The git-side steps (commit, branch, push, PR) are fully implemented.

The typed approval gate is non-bypassable. There is no -y flag. If stdin is
not a TTY the script exits non-zero rather than auto-approving.

Usage:
    python scripts/close_prompt.py [--dry-run] [--no-cross-review]
                                   [--slug part-01/workflow-harness]
                                   [--part 1]
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
SESSION_TEMPLATE = SESSIONS_DIR / "_template.md"

APPROVAL_STRINGS = {"approve", "APPROVE"}
DEPLOY_TOUCH_PATTERNS = (
    "infra/",
    "helm/",
    "terraform/",
    "Dockerfile",
    "docker-compose",
    "scripts/setup_",
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
    return any(any(p in f for p in DEPLOY_TOUCH_PATTERNS) for f in files)


def generate_commit_message(files: list[str], slug: str) -> str:
    # Pick a Conventional Commits type from staged paths.
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
    subagent_summary: str,
    cross_review_path: pathlib.Path | None,
    adversarial_summary: str,
    files: list[str],
) -> pathlib.Path:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    date = dt.date.today().isoformat()
    # Match the prompt number from the slug if possible.
    prompt_num_match = re.search(r"prompt-?(\d+)", slug)
    prompt_num = prompt_num_match.group(1) if prompt_num_match else f"{part:02d}"
    journal_name = f"{date}-prompt-{prompt_num}-{slug.replace('/', '-')}.md"
    path = SESSIONS_DIR / journal_name

    template_body = ""
    if SESSION_TEMPLATE.exists():
        template_body = SESSION_TEMPLATE.read_text(encoding="utf-8")

    summary = textwrap.dedent(
        f"""\
        # Session journal — {date} — {slug}

        - **Date:** {date}
        - **Part:** {part}
        - **Slug:** {slug}
        - **Files touched ({len(files)}):**
        {chr(10).join(f"  - {f}" for f in files[:60])}
        {"  - ... and more" if len(files) > 60 else ""}

        ## Subagent verdicts

        {subagent_summary or "_See inline reports during /close-prompt run._"}

        ## Cross-model review

        {f"See `{cross_review_path.relative_to(REPO_ROOT)}`" if cross_review_path else "_Not run._"}

        ## Adversarial review

        {adversarial_summary or "_See inline report during /close-prompt run._"}

        ---

        """
    )
    path.write_text(summary + template_body, encoding="utf-8")
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
    # Use --no-verify? No — we want hooks to run. Sign if gitsign is configured.
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


def main() -> int:
    load_dotenv_if_present()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-cross-review", action="store_true")
    parser.add_argument("--slug", default=None)
    parser.add_argument("--part", type=int, default=None)
    args = parser.parse_args()

    files = git_staged_files()
    if not files:
        sys.exit("No staged changes. Stage what you mean to commit and try again.")

    part = args.part or infer_part_number()
    branch_now = git_current_branch()
    slug = args.slug or infer_slug_from_branch(branch_now, default="workflow-harness")

    print(f"[part] {part}")
    print(f"[branch] {branch_now or '(detached)'}")
    print(f"[slug] {slug}")
    print(f"[files staged] {len(files)}")

    # Step 2 — subagent reviews (stubbed; handled by Claude session).
    subagent_summary = (
        "Subagent reviews are run by the Claude session that invokes "
        "/close-prompt. This script records their outputs in the session "
        "journal. If you are running this directly, complete the subagent "
        "passes before approving."
    )
    print("\n[subagents] Run reviewer, architect-guard, doc-sync, "
          "regulator-readability, benchmark-checker, second-opinion via the "
          "Claude session. Block on any BLOCK verdict.")

    # Step 3 — cross-model review.
    cross_review_path: pathlib.Path | None = None
    azure_ready = all(
        os.environ.get(v)
        for v in (
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_OPENAI_API_VERSION",
        )
    )
    if not args.no_cross_review and azure_ready:
        print("\n[cross-review] Calling scripts/cross_review.py --target staged")
        r = run([sys.executable, str(REPO_ROOT / "scripts" / "cross_review.py"),
                 "--target", "staged"])
        if r.returncode == 0:
            out = r.stdout.strip().splitlines()
            if out:
                cross_review_path = pathlib.Path(out[-1])
                print(f"[cross-review] wrote {cross_review_path}")
        else:
            print(f"[cross-review] failed:\n{r.stderr}")
    else:
        print("[cross-review] skipped (--no-cross-review or one of the four "
              "AZURE_OPENAI_* env vars is missing — see .env.example).")

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
        Cross-review:  {cross_review_path if cross_review_path else 'not run'}

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
        subagent_summary=subagent_summary,
        cross_review_path=cross_review_path,
        adversarial_summary=adversarial_summary,
        files=files,
    )
    print(f"[journal] wrote {journal.relative_to(REPO_ROOT)}")
    # Stage the journal so it lands in the same commit.
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
