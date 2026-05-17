"""Regression tests for close_prompt.py carry-over fixes (Prompts 1, 2, 3).

Carry-over #1 (cross-review handling, Prompt 1):
    1a. A non-zero exit from cross_review.py must hard-fail the closeout.
    1b. On success, the produced docs/reviews file must be staged so it lands
        in the same commit as the change it documents.
    1c. --skip-cross-review-with-reason "<reason>" is the only sanctioned
        bypass; the reason must be non-empty and propagated to the journal.

Carry-over #2 (deploy-test trigger, Prompt 1):
    The trigger uses anchored regexes, not substring matching. Generic
    harness scripts (scripts/setup_hooks.sh, scripts/bootstrap_github_labels.sh)
    must NOT trigger. Real infra paths (infra/, helm/, terraform/, docker/,
    Dockerfile, compose*.yaml) MUST trigger.

Prompt-3 carry-over fixes:
    #1 (journal filename): write_session_journal takes an explicit `prompt`
       argument and the filename uses it directly. The Prompt 2 journal was
       mis-named `prompt-01-...` by the prior slug-regex heuristic and had
       to be renamed in PR #17 after the fact.
    #3 (triage-line gate): check_triage_filled raises if the cross-review
       file still contains the `_TODO: human-filled` placeholder.
    #4 (cross-review slug stability): cross_review.py's collect_target accepts
       a slug_override so same-day re-runs from different prompts land at
       distinct filenames rather than all overwriting `<date>-staged-diff.md`.

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
import cross_review as cr


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

    journal = cp.write_session_journal(
        slug="supply-chain-and-secrets",
        part=1,
        prompt=2,
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
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)

    journal = cp.write_session_journal(
        slug="supply-chain-and-secrets",
        part=1,
        prompt=2,
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
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)

    journal = cp.write_session_journal(
        slug="supply-chain-and-secrets",
        part=1,
        prompt=2,
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
    # `## Subagent verdicts` was removed from the script-generated body in
    # Prompt-3 carry-over fix #5 — that section now lives only in the operator-
    # edited template appended after the script-generated block.
    required_headings = [
        "# Session journal — ",
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


# -- Prompt-3 carry-over #1: journal filename uses prompt number, not part ----


def test_journal_filename_uses_prompt_number_not_part(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for the Prompt 2 mis-naming: the journal file was named
    `prompt-01-...` because the script inferred the prompt number from the
    branch's part-NN/ slug. write_session_journal now takes an explicit
    `prompt` argument and uses it directly in the filename."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(cp, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)

    journal = cp.write_session_journal(
        slug="uv-project-and-python-tooling",
        part=1,
        prompt=3,
        cross_review_path=None,
        cross_review_skip_reason="VPN off",
        adversarial_summary="no objections",
        files=["pyproject.toml"],
    )
    name = journal.name
    assert "prompt-03" in name, (
        f"Expected `prompt-03` in journal filename, got {name!r}."
    )
    assert "prompt-01" not in name, (
        f"Journal filename {name!r} contains `prompt-01`; the regression "
        "from the Prompt 2 mis-naming bug has returned."
    )


# -- Prompt-3 carry-over #3: triage-line enforcement --------------------------


def test_triage_line_enforcement_blocks_on_unfilled_todo(
    tmp_path: pathlib.Path,
) -> None:
    """check_triage_filled raises if the cross-review file still has the
    `_TODO: human-filled` placeholder. The Prompt 2 retrospective noted that
    the placeholder was being committed unchanged, defeating the audit-trail
    purpose of the triage line."""
    review = tmp_path / "fixture-review.md"
    review.write_text(
        "# Cross-model review — fixture\n\n"
        "## Summary\nbody\n\n"
        "## Triage\n\n"
        "_TODO: human-filled. Disposition each finding above as accept / "
        "defer / reject, with reason._\n"
    )
    with pytest.raises(RuntimeError, match="placeholder"):
        cp.check_triage_filled(review)


def test_triage_line_enforcement_passes_when_filled(
    tmp_path: pathlib.Path,
) -> None:
    """Positive case: a triage section with real dispositions passes."""
    review = tmp_path / "filled-review.md"
    review.write_text(
        "# Cross-model review — fixture\n\n"
        "## Summary\nbody\n\n"
        "## Triage\n\n"
        "- Finding 1: accept — adopting the rename in this PR.\n"
        "- Finding 2: defer — tracked in DEFERRED.md.\n"
    )
    # Should not raise.
    cp.check_triage_filled(review)


def test_triage_gate_ignores_marker_in_summary(
    tmp_path: pathlib.Path,
) -> None:
    """Post-Prompt-3 adversarial fix: the gate scans only the `## Triage`
    section. A quoted instance of the marker in `## Summary` (or any other
    non-Triage section) must not block. Earlier whole-file substring check
    would have falsely jammed the gate when a future cross-review quoted the
    marker while discussing the gate itself."""
    review = tmp_path / "meta-review.md"
    review.write_text(
        "# Cross-model review — fixture\n\n"
        "## Summary\n\n"
        "The closeout pipeline gates approval on the literal string "
        "`_TODO: human-filled` appearing in the Triage section. This is a "
        "deliberate, in-band marker.\n\n"
        "## Disagreements with primary review\n\n"
        "None.\n\n"
        "## Risks not flagged elsewhere\n\n"
        "None.\n\n"
        "## Recommended actions\n\n"
        "None.\n\n"
        "## Triage\n\n"
        "- Finding 1: accept — the gate marker is documented as intended.\n"
    )
    # Should not raise — the marker appears in Summary but Triage is dispositioned.
    cp.check_triage_filled(review)


def test_triage_gate_blocks_on_missing_triage_section(
    tmp_path: pathlib.Path,
) -> None:
    """Malformed file: no `## Triage` heading at all. cross_review.py's
    enforce_sections should have written one; if it didn't, the closeout must
    refuse rather than silently pass."""
    review = tmp_path / "malformed-review.md"
    review.write_text(
        "# Cross-model review — fixture\n\n"
        "## Summary\n\nbody, but no Triage section follows.\n"
    )
    with pytest.raises(RuntimeError, match="no `## Triage` section"):
        cp.check_triage_filled(review)


def test_triage_gate_uses_last_triage_section(
    tmp_path: pathlib.Path,
) -> None:
    """Hand-edited files may end up with two `## Triage` sections (e.g., the
    operator pasted a fresh template below the original). The gate uses the
    LAST one — that is the operator's most recent state. If the last one is
    dispositioned, approval proceeds even if the first one still has the TODO
    placeholder."""
    review = tmp_path / "duplicated-triage.md"
    review.write_text(
        "# Cross-model review — fixture\n\n"
        "## Summary\nbody\n\n"
        "## Triage\n\n"
        "_TODO: human-filled. Disposition each finding above as accept / "
        "defer / reject, with reason._\n\n"
        "## Triage\n\n"
        "- Finding 1: accept — superseded the earlier draft above.\n"
    )
    # Should not raise — the LAST Triage section is dispositioned.
    cp.check_triage_filled(review)

    # And the inverse: if the last Triage section still has the TODO, block,
    # even though the first one is dispositioned.
    review.write_text(
        "# Cross-model review — fixture\n\n"
        "## Summary\nbody\n\n"
        "## Triage\n\n"
        "- Finding 1: accept — operator filled this in, then pasted a fresh "
        "template below by accident.\n\n"
        "## Triage\n\n"
        "_TODO: human-filled. Disposition each finding above as accept / "
        "defer / reject, with reason._\n"
    )
    with pytest.raises(RuntimeError, match="placeholder"):
        cp.check_triage_filled(review)


# -- Prompt-3 carry-over #4: cross-review slug stability ----------------------


def test_cross_review_slug_stability(monkeypatch: pytest.MonkeyPatch) -> None:
    """collect_target("staged", slug_override=...) must return the same slug
    for repeated calls with the same override, and different slugs for
    different overrides. Without slug_override the output collapses to
    `<date>-staged-diff.md` and same-day re-runs overwrite each other."""

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="diff --git a/x b/x\n+changed\n",
            stderr="",
        )

    monkeypatch.setattr(cr.subprocess, "run", fake_run)

    _, slug_foo_first = cr.collect_target("staged", slug_override="foo")
    _, slug_foo_second = cr.collect_target("staged", slug_override="foo")
    _, slug_bar = cr.collect_target("staged", slug_override="bar")

    assert slug_foo_first == slug_foo_second, (
        "Same slug_override must produce a stable slug; got "
        f"{slug_foo_first!r} then {slug_foo_second!r}."
    )
    assert slug_foo_first != slug_bar, (
        "Different slug_overrides must produce different slugs; got "
        f"{slug_foo_first!r} for 'foo' and {slug_bar!r} for 'bar'."
    )

    # And the default (no override) is still the legacy `staged-diff` slug.
    _, slug_default = cr.collect_target("staged", slug_override=None)
    assert slug_default == "staged-diff"

def test_journal_does_not_contain_template_placeholder_markers(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The generated journal must be a complete, self-contained document.

    Regression for a bug surfaced during Prompt 3 closeout:
    write_session_journal concatenated docs/sessions/_template.md to the
    bottom of the generated journal, leaving every output with a duplicated
    H1 (`# Session journal — <YYYY-MM-DD> — <slug>`) and visible
    `<YYYY-MM-DD>`-style placeholder markers. The fix: emit the complete
    structure inline; do not read or append the template file at runtime.

    The test asserts: no template-style placeholders leak into the journal,
    and exactly one H1 heading exists.
    """
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(cp, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(cp, "REPO_ROOT", tmp_path)
    journal = cp.write_session_journal(
        slug="example-prompt",
        part=1,
        prompt=99,
        cross_review_path=None,
        cross_review_skip_reason="test fixture",
        adversarial_summary="no objections",
        files=["pyproject.toml", "scripts/example.py"],
    )
    body = journal.read_text(encoding="utf-8")

    # No template-shape placeholders leaked in.
    for marker in ("<YYYY-MM-DD>",):
        assert marker not in body, (
            f"Template placeholder {marker!r} leaked into generated journal:\n"
            f"{body}"
        )

    # Exactly one H1 heading (the metadata one — no duplicate from a
    # concatenated template body).
    h1_lines = [
        line for line in body.splitlines()
        if line.startswith("# ") and not line.startswith("## ")
    ]
    assert len(h1_lines) == 1, (
        f"Expected exactly one H1 heading, found {len(h1_lines)}: {h1_lines}"
    )
    assert "# Session journal" in h1_lines[0], (
        f"Unexpected H1 content: {h1_lines[0]!r}"
    )
