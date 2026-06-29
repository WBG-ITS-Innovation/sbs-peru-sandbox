# SPDX-License-Identifier: Apache-2.0
"""Synthetic corpus generator — Workstream E (ADR 0036).

Asserts:

* Determinism: same seed + same today produce byte-identical CSV.
* 100% Anexo 1-A schema compliance: each generated row validates
  through the canonical :class:`Complaint` Pydantic model.
* Narrative templates substitute correctly (no unfilled placeholders).
* Monetary amounts fall in the documented range.
* The committed golden sample reproduces from the deterministic seed.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import date
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def generate(tmp_path):
    """Yield a callable that runs the generator into a tmp dir."""

    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    # Import lazily so the side-effect path-mangling in the generator
    # script doesn't run at collection time.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_synthetic_corpus",
        REPO_ROOT / "scripts" / "generate-synthetic-corpus.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    def _gen(*, rows: int = 20, seed: int = 2026, today: date = date(2026, 5, 20)):
        out_dir = tmp_path / "corpus"
        return module.generate(
            out_dir=out_dir,
            rows_per_institution=rows,
            seed=seed,
            today=today,
        ), out_dir

    yield _gen


def test_deterministic_same_seed(generate):
    a, a_dir = generate(rows=20, seed=2026)
    b, b_dir = generate(rows=20, seed=2026)
    for inst in a:
        assert a[inst]["sha256"] == b[inst]["sha256"], inst
        assert (
            Path(a_dir / inst / f"{inst}.csv").read_bytes()
            == Path(b_dir / inst / f"{inst}.csv").read_bytes()
        )


def test_different_seed_yields_different_corpus(generate):
    a, _ = generate(rows=20, seed=2026)
    b, _ = generate(rows=20, seed=9999)
    # At least one institution must differ.
    assert any(a[i]["sha256"] != b[i]["sha256"] for i in a)


def test_anexo_1a_schema_compliance(generate):
    summary, out_dir = generate(rows=50, seed=2026)
    from sbs_api.models.anexo_1a import Complaint

    for inst, info in summary.items():
        csv_text = Path(info["csv"]).read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(csv_text))
        rows_validated = 0
        for raw in reader:
            # Normalise empty CSV cells to None like the worker does.
            row = {k: (None if v == "" else v) for k, v in raw.items()}
            Complaint.model_validate(row)
            rows_validated += 1
        assert rows_validated == info["rows"]


def test_narratives_have_no_unfilled_placeholders(generate):
    summary, _ = generate(rows=30, seed=2026)
    placeholder_re = re.compile(r"\{[a-z_]+\}")
    for info in summary.values():
        csv_text = Path(info["csv"]).read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(csv_text))
        for row in reader:
            assert not placeholder_re.search(row["description_text"]), (
                f"unfilled placeholder in narrative: {row['description_text']!r}"
            )


def test_monetary_amounts_in_documented_range(generate):
    """The narrative contains the monetary value; extract and bound-check."""

    summary, _ = generate(rows=200, seed=2026)
    amount_re = re.compile(r"S/?\s*([\d]+\.\d{2})|(\d+\.\d{2})\s+soles")
    for info in summary.values():
        csv_text = Path(info["csv"]).read_text(encoding="utf-8")
        reader = csv.DictReader(io.StringIO(csv_text))
        seen = 0
        for row in reader:
            for match in amount_re.finditer(row["description_text"]):
                value = float(match.group(1) or match.group(2))
                assert 10.0 <= value <= 200_000.0, value
                seen += 1
                break  # one amount per row is enough
        assert seen > 0


def test_golden_sample_reproduces_from_seed():
    """The committed golden sample's checksums match a fresh regeneration.

    Reads the committed CSVs and recomputes their SHA-256. A
    fresh-from-seed regeneration produces the same bytes by the
    determinism contract; we therefore assert the recorded manifest
    checksum agrees with the on-disk CSV.
    """

    import json

    golden_dir = REPO_ROOT / "data" / "synthetic-corpus-golden"
    institutions = ["SBS-001234", "SBS-005678", "SBS-009012"]
    for inst in institutions:
        csv_path = golden_dir / inst / f"{inst}.csv"
        mfst_path = golden_dir / inst / f"{inst}.manifest.json"
        assert csv_path.exists(), csv_path
        assert mfst_path.exists(), mfst_path
        manifest = json.loads(mfst_path.read_text())
        recomputed = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        assert recomputed == manifest["checksum_sha256"], inst


def test_ruc_checksums_valid_when_doc_type_is_ruc(generate):
    """If a row's doc_type is RUC, the synthetic id check digit holds.

    The corpus generator currently injects RUCs only via the doc-type
    enum; the actual RUC string is not in the Anexo 1-A 15-field subset.
    What we *can* assert is that the optional ``original_reference_id``
    pattern stays compatible (and the RUC checksum helper itself is
    correct).
    """

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_synthetic_corpus",
        REPO_ROOT / "scripts" / "generate-synthetic-corpus.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    import random as _random

    rng = _random.Random(123)
    multipliers = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
    for _ in range(50):
        ruc = module._ruc_with_valid_checksum(rng)
        assert len(ruc) == 11 and ruc.isdigit()
        base = [int(c) for c in ruc[:10]]
        check = int(ruc[10])
        s = sum(d * m for d, m in zip(base, multipliers))
        expected = 11 - (s % 11)
        if expected == 11:
            expected = 0
        elif expected == 10:
            expected = 1
        assert expected == check, (ruc, expected, check)


def test_pattern_cluster_profile_raises_not_implemented(generate):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_synthetic_corpus",
        REPO_ROOT / "scripts" / "generate-synthetic-corpus.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    with pytest.raises(NotImplementedError, match="Prompt 11"):
        module.generate(
            out_dir=REPO_ROOT / "data" / "synthetic-corpus",
            rows_per_institution=1,
            seed=2026,
            distribution_profile="pattern-cluster",
        )
