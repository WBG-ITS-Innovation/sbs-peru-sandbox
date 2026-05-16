"""Regression tests for the two close_prompt.py carry-over fixes from Prompt 1.

Carry-over #1 (cross-review handling):
    1a. A non-zero exit from cross_review.py must hard-fail the closeout.
    1b. On success, the produced docs/reviews file must be staged so it lands
        in the same commit as the change it documents.
    1c. --skip-cross-review-with-reason "<reason>" is the only sanctioned
        bypass; the reason must be non-empty and propagated to the journal.

Carry-over #2 (deploy-test trigger):
    The trigger uses anchored regexes, not substring matching. Generic
    harness scripts (scripts/setup_hooks.sh, scripts/bootstrap_github_labels.sh)
    must NOT trigger. Real infra paths (infra/, helm/, terraform/, docker/,
    Dockerfile, compose*.yaml) MUST trigger.

These tests do not push to git or call Azure. They patch subprocess.run and
exercise the in-process functions directly.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
from unittest import mock

import pytest

import close_prompt as cp


# -- carry-over #2: deploy_touched regex tests --------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "scripts/setup_hooks.sh",
        "scripts/bootstrap_github_labels.sh",
        "scripts/close_prompt.py",
        "docs/setup/corporate-proxy-and-zscaler.md",
        "docs/PLAN.md",
        "README.md",
        ".github/workflows/secret-scan.yml",
        "tests/test_close_prompt.py",
    ],
)
def test_deploy_touched_does_not_match_harness_paths(path: str) -> None:
    assert cp.deploy_touched([path]) is False, (
        f"{path} unexpectedly triggered the deploy-test warning. "
        "Check DEPLOY_TOUCH_REGEXES — substring matching is the old bug."
    )


@pytest.mark.parametrize(
    "path",
    [
        "infra/k8s/values.yaml",
        "infra/network/policy.yaml",
        "helm/sbs-suptech/Chart.yaml",
        "helm/sbs-suptech/values-azure.yaml",
        "terraform/azure/main.tf",
        "terraform/baremetal/postgres.tf",
        "docker/api/Dockerfile",
        "docker/vllm/Dockerfile",
        "Dockerfile",
        "compose.yaml",
        "compose.yml",
        "docker-compose.yaml",
        "docker-compose.dev.yaml",
    ],
)
def test_deploy_touched_matches_real_infra_paths(path: str) -> None:
    assert cp.deploy_touched([path]) is True, (
        f"{path} should have triggered the deploy-test warning."
    )


def test_deploy_touched_mixed_set() -> None:
    """A single infra path among many non-infra paths still triggers."""
    files = [
        "docs/PLAN.md",
        "scripts/setup_hooks.sh",
        "helm/sbs-suptech/Chart.yaml",
        ".github/dependabot.yml",
    ]
    assert cp.deploy_touched(files) is True


def test_deploy_touched_empty() -> None:
    assert cp.deploy_touched([]) is False


# -- carry-over #1a: cross-review failure must hard-fail ----------------------


def _set_azure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in cp.AZURE_ENV_VARS:
        monkeypatch.setenv(v, "test-value")


def _make_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_cross_review_failure_hard_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-zero exit from cross_review.py raises RuntimeError.

    Regression for Prompt 1 silent-tolerance bug.
    """
    _set_azure_env(monkeypatch)
    monkeypatch.setattr(
        cp,
        "run",
        lambda cmd, **kw: _make_completed(
            1, stdout="", stderr="CERTIFICATE_VERIFY_FAILED"
        ),
    )
    with pytest.raises(RuntimeError, match="Cross-review failed"):
        cp.run_cross_review(skip_reason=None)


def test_cross_review_missing_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """If env is missing and no skip flag is given, the closeout fails loudly
    rather than silently skipping (the Prompt 1 behaviour)."""
    for v in cp.AZURE_ENV_VARS:
        monkeypatch.delenv(v, raising=False)
    with pytest.raises(RuntimeError, match="missing env vars"):
        cp.run_cross_review(skip_reason=None)


# -- carry-over #1b: successful review file must be staged --------------------


def test_cross_review_success_stages_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    _set_azure_env(monkeypatch)

    fake_review = tmp_path / "fake-review.md"
    fake_review.write_text("# Cross-model review — staged-diff\n\nbody\n")

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        # First call: cross_review.py — return 0 with the path on stdout.
        if any("cross_review.py" in str(c) for c in cmd):
            return _make_completed(0, stdout=f"{fake_review}\n")
        # Second call: `git add <path>` — succeed.
        if cmd[:2] == ["git", "add"]:
            return _make_completed(0)
        return _make_completed(0)

    monkeypatch.setattr(cp, "run", fake_run)

    path, skip_reason = cp.run_cross_review(skip_reason=None)
    assert path == fake_review
    assert skip_reason is None
    # The git add must have happened and must reference the review file path.
    add_calls = [c for c in calls if c[:2] == ["git", "add"]]
    assert add_calls, "expected `git add <review_file>` to be called"
    assert str(fake_review) in add_calls[-1]


def test_cross_review_success_but_missing_file_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """If cross_review.py exits 0 but the promised file is missing, fail."""
    _set_azure_env(monkeypatch)
    missing = tmp_path / "never-written.md"
    monkeypatch.setattr(
        cp,
        "run",
        lambda cmd, **kw: _make_completed(0, stdout=f"{missing}\n"),
    )
    with pytest.raises(RuntimeError, match="expected file is missing"):
        cp.run_cross_review(skip_reason=None)


def test_cross_review_success_but_empty_file_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    _set_azure_env(monkeypatch)
    empty = tmp_path / "empty-review.md"
    empty.write_text("")
    monkeypatch.setattr(
        cp,
        "run",
        lambda cmd, **kw: _make_completed(0, stdout=f"{empty}\n"),
    )
    with pytest.raises(RuntimeError, match="empty file"):
        cp.run_cross_review(skip_reason=None)


# -- carry-over #1c: --skip-cross-review-with-reason behaviour ----------------


def test_skip_with_reason_returns_skip_and_no_path() -> None:
    path, reason = cp.run_cross_review(skip_reason="VPN off, no Azure access")
    assert path is None
    assert reason == "VPN off, no Azure access"


def test_skip_with_empty_reason_raises() -> None:
    with pytest.raises(RuntimeError, match="non-empty reason"):
        cp.run_cross_review(skip_reason="")


def test_skip_with_whitespace_reason_raises() -> None:
    with pytest.raises(RuntimeError, match="non-empty reason"):
        cp.run_cross_review(skip_reason="   \t  ")


def test_journal_records_skip_reason(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The skip reason lands in the journal under the cross-review section."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(cp, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(cp, "SESSION_TEMPLATE", sessions / "_template.md")  # not present

    journal = cp.write_session_journal(
        slug="supply-chain-and-secrets",
        part=1,
        subagent_summary="reviewer: APPROVE",
        cross_review_path=None,
        cross_review_skip_reason="VPN off",
        adversarial_summary="no objections",
        files=["scripts/close_prompt.py"],
    )
    body = journal.read_text(encoding="utf-8")
    assert "## Cross-model review — triage line" in body
    assert "SKIPPED: VPN off" in body


def test_journal_records_review_path(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    reviews = tmp_path / "docs" / "reviews"
    reviews.mkdir(parents=True)
    review = reviews / "2026-05-16-staged-diff.md"
    review.write_text("# review\n")

    monkeypatch.setattr(cp, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(cp, "SESSION_TEMPLATE", sessions / "_template.md")
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)

    journal = cp.write_session_journal(
        slug="supply-chain-and-secrets",
        part=1,
        subagent_summary="reviewer: APPROVE",
        cross_review_path=review,
        cross_review_skip_reason=None,
        adversarial_summary="no objections",
        files=["scripts/close_prompt.py"],
    )
    body = journal.read_text(encoding="utf-8")
    assert "## Cross-model review — triage line" in body
    assert "docs/reviews/2026-05-16-staged-diff.md" in body
    assert "SKIPPED" not in body


# -- journal output formatting: regression for the heredoc-indent bug --------
#
# The 2026-05-16 Prompt 1 journal was written with six-space leading
# whitespace because an earlier version of write_session_journal used a
# non-dedented heredoc. Markdown-rendering tools then treated each line as
# preformatted text. This regression guards against that recurrence.


def _build_journal_for_format_test(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cross_review_path: pathlib.Path | None,
    cross_review_skip_reason: str | None,
) -> str:
    sessions = tmp_path / "sessions"
    sessions.mkdir(exist_ok=True)
    monkeypatch.setattr(cp, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(cp, "SESSION_TEMPLATE", sessions / "_template.md")
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)

    journal = cp.write_session_journal(
        slug="supply-chain-and-secrets",
        part=1,
        subagent_summary="reviewer: APPROVE\narchitect-guard: APPROVE",
        cross_review_path=cross_review_path,
        cross_review_skip_reason=cross_review_skip_reason,
        adversarial_summary="no material objections",
        files=["scripts/close_prompt.py", "tests/test_close_prompt.py"],
    )
    return journal.read_text(encoding="utf-8")


def _structural_lines(body: str) -> list[tuple[int, str]]:
    """Return (line_number, line) pairs for non-blank lines that are NOT
    inside a fenced code block or an explicitly-bulleted file list. These
    are the lines that must be flush-left."""
    lines = body.splitlines()
    out: list[tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped:
            continue
        # The bulleted file-list lines are intentionally indented by two
        # spaces ("  - <file>"), as is the trailing "... and more" line.
        # Skip those rather than try to second-guess them.
        if stripped.startswith("- ") or stripped.startswith("* "):
            continue
        out.append((i, line))
    return out


def test_journal_headers_are_flush_left(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Heading and prose lines start at column 1, not column 7."""
    body = _build_journal_for_format_test(
        tmp_path,
        monkeypatch,
        cross_review_path=None,
        cross_review_skip_reason="VPN off",
    )
    bad = [
        (i, line)
        for (i, line) in _structural_lines(body)
        if line != line.lstrip()
    ]
    assert not bad, (
        "These lines have unexpected leading whitespace; "
        "the heredoc indent bug has returned:\n"
        + "\n".join(f"  line {i}: {line!r}" for (i, line) in bad)
    )


def test_journal_headings_present_and_unindented(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The structural Markdown headings must start at column 1."""
    body = _build_journal_for_format_test(
        tmp_path,
        monkeypatch,
        cross_review_path=None,
        cross_review_skip_reason="VPN off",
    )
    required_headings = [
        "# Session journal — ",
        "## Subagent verdicts",
        "## Cross-model review — triage line",
        "## Adversarial review",
    ]
    for heading in required_headings:
        # Each heading occurs at the start of some line, with no leading space.
        matches = [
            line for line in body.splitlines() if line.startswith(heading)
        ]
        assert matches, (
            f"Heading {heading!r} is missing or indented. "
            f"Found instead: "
            f"{[line for line in body.splitlines() if heading in line]}"
        )


def test_journal_no_six_space_indent_anywhere(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Belt-and-braces. The exact failure mode in Prompt 1 was six-space
    leading whitespace. Guard for that specifically, in addition to the
    general flush-left check above."""
    for path_kw in (
        {"cross_review_path": None, "cross_review_skip_reason": "VPN off"},
        {"cross_review_path": None, "cross_review_skip_reason": None},
    ):
        body = _build_journal_for_format_test(tmp_path, monkeypatch, **path_kw)
        # tmp_path is per-test; clean the sessions dir between iterations.
        for f in (tmp_path / "sessions").glob("*"):
            f.unlink()
        offenders = [
            line for line in body.splitlines() if line.startswith("      ")
        ]
        assert not offenders, (
            f"Six-space-indented lines found in journal body "
            f"(input: {path_kw}):\n" + "\n".join(repr(x) for x in offenders)
        )
