"""Determinism check for the demo replay corpus generation.

CSV inputs to ``scripts/demo.sh`` must be byte-identical across runs
at the same ``--seed``. Webhook signature timestamps are NOT
deterministic (timestamps are current-time per request), but the
synthetic CSVs that feed the upload step must be.

**Known limitation (Prompt 9 carry-forward to v0.2):** the corpus
generator's determinism is **intraday only** — `received_date`
defaults are wall-clock-derived, so two runs at the same seed on
different UTC dates produce different bytes. The test below catches
the intraday case; cross-day determinism requires the generator to
accept ``--window-start``/``--window-end`` flags and use them in
place of ``date.today()``. Tracked for v0.2.

Two-run check: generate the corpus twice into separate tmp dirs at
the same seed, compare the SHA-256 of every produced CSV. A
mismatch means the corpus generator has a hidden source of
non-determinism (a wall-clock-derived field, a missing seed of a
sub-generator, etc.) that would break the demo's "byte-identical
on any reviewer's machine" claim within a single day.

The test does not require docker, the dev stack, or any live
compose service — it only exercises the corpus generator. The full
live-stack exit gate (stage-h-full) is exercised by
``scripts/demo.sh`` itself in the closeout's live-stack acceptance
log; this test is the contract-level companion (stage-h-contract).
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

DEMO_SEED = "20260520"
SMALL_SCALE_ROWS_PER_INST = 17

# The corpus generator names each institution's CSV path as
# <corpus-dir>/<institution_id>/<institution_id>.csv.
DEMO_INSTITUTIONS = ["SBS-001234", "SBS-005678", "SBS-009012"]


def _generate_corpus(out_dir: pathlib.Path, seed: str, rows: int) -> None:
    """Invoke the synthetic corpus generator into ``out_dir``."""

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "scripts/generate-synthetic-corpus.py",
            "--out",
            str(out_dir),
            "--rows-per-institution",
            str(rows),
            "--seed",
            seed,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"generate-synthetic-corpus.py failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_demo_corpus_is_byte_identical_across_runs_at_same_seed(tmp_path):
    """Two corpus generations at the same seed produce byte-identical CSVs.

    NOTE: intraday determinism only — see module docstring. The
    cross-day case is a known limitation tracked for v0.2.
    """

    run_a = tmp_path / "run-a"
    run_b = tmp_path / "run-b"
    run_a.mkdir()
    run_b.mkdir()

    _generate_corpus(run_a, DEMO_SEED, SMALL_SCALE_ROWS_PER_INST)
    _generate_corpus(run_b, DEMO_SEED, SMALL_SCALE_ROWS_PER_INST)

    for institution_id in DEMO_INSTITUTIONS:
        csv_a = run_a / institution_id / f"{institution_id}.csv"
        csv_b = run_b / institution_id / f"{institution_id}.csv"
        assert csv_a.is_file(), f"missing corpus CSV: {csv_a}"
        assert csv_b.is_file(), f"missing corpus CSV: {csv_b}"
        # SHA-256 is the byte-identity check.
        assert _sha256(csv_a) == _sha256(csv_b), (
            f"corpus CSV for {institution_id} differs between runs at "
            f"the same seed; non-determinism in the generator breaks the "
            f"demo's byte-identical reproducibility claim"
        )


def test_demo_corpus_changes_when_seed_changes(tmp_path):
    """Different seeds must produce different bytes — proves the seed is used."""

    run_a = tmp_path / "seed-a"
    run_b = tmp_path / "seed-b"
    run_a.mkdir()
    run_b.mkdir()

    _generate_corpus(run_a, "20260520", SMALL_SCALE_ROWS_PER_INST)
    _generate_corpus(run_b, "20260521", SMALL_SCALE_ROWS_PER_INST)

    diffs = 0
    for institution_id in DEMO_INSTITUTIONS:
        csv_a = run_a / institution_id / f"{institution_id}.csv"
        csv_b = run_b / institution_id / f"{institution_id}.csv"
        if _sha256(csv_a) != _sha256(csv_b):
            diffs += 1
    assert diffs == len(DEMO_INSTITUTIONS), (
        "every institution's CSV should differ between seeds; got "
        f"{diffs} of {len(DEMO_INSTITUTIONS)} institutions changing"
    )


def test_demo_sh_help_works():
    """Sanity check: scripts/demo.sh --help exits 0 and prints usage."""

    result = subprocess.run(
        ["bash", "scripts/demo.sh", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "--scale" in result.stdout
    assert "--seed" in result.stdout
    assert "--max-wait" in result.stdout


def test_demo_replay_module_imports():
    """The orchestrator module imports without error.

    Catches import-time syntax errors and missing dependencies
    without requiring docker or the live stack.
    """

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-c",
            "import scripts.demo_replay  # noqa: F401",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Try without the package prefix (scripts/ is not a package by default).
        result = subprocess.run(
            ["uv", "run", "python", "scripts/demo_replay.py", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, (
        f"demo_replay.py failed to import / --help:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
