# SPDX-License-Identifier: Apache-2.0
"""No real financial institution is named in any committed data fixture.

`DATA_PROVENANCE.md` asserts that every complaint record in the repository
is generated and that no real institution is named. Before 2026-08-14 that
was false: `app/src/lib/rr1-2025.json` attributed month-by-month complaint
volumes to 50 named, real, regulated Peruvian entities, and
`scripts/build_journey_fixtures.py` wrote four named real banks into 80 real
complaint narratives. A pre-publication sweep caught it. Nothing in the
secret-scanner stack could have: gitleaks and detect-secrets look for
credentials, and third-party data is not a credential.

This is the gate for that class of defect. It is the only automated check
standing between a re-extracted workbook and a public repository, so it is
written to fail loudly rather than skip.

Two matching strategies, because one does not fit both cases:

* **Brand names** — the five the sweep named — match case-insensitively on
  word boundaries. A contributor could reintroduce these in any casing, in
  prose or in a value.
* **Workbook labels** — the 45 institution rows of the RR1 Empresa sheet —
  match case-sensitively, exactly as the workbook spelled them. The failure
  mode being guarded against is an extract reappearing, and an extract
  carries the workbook's own casing. Matching these case-insensitively would
  make ordinary Spanish trip the gate: `ALTERNATIVA` and `NACION` are real
  institution labels *and* ordinary words.

Note on method, from the sweep: `git grep -IlE "\\b(BCP|BBVA)\\b"` returns
nothing while `git grep -Il BBVA` returns three files — git's ERE does not
honour `\\b` and fails silently. This test uses Python's `re`, which does.
A prior review that relied on word-boundary git-greps would have missed
both blockers.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# Real institutions the sweep found written into narrative text by
# scripts/build_journey_fixtures.py's _FAKE_ENTITIES and _FAKE_ORGS.
# Essalud is a state health-insurance body, named in a payroll-deduction
# dispute; the rest are banks.
BRAND_NAMES: tuple[str, ...] = (
    "BCP",
    "Interbank",
    "BBVA",
    "Scotiabank",
    "Essalud",
    "Caja Arequipa",
    "Caja Cusco",
)

# The 45 institution rows of the RR1 Empresa sheet, verbatim as the
# workbook spelled them. The five segment heading rows that sheet also
# carried — Banco, Financiera, Caja municipal, Caja rural, Empresa de
# Crédito — are deliberately NOT here: they are regulatory classes of
# supervised entity, not entities, and they appear legitimately
# throughout the generated fixtures and the code.
WORKBOOK_LABELS: tuple[str, ...] = (
    "AGROBANCO",
    "ALFIN BANCO",
    "BANBIF",
    "BANCO DE COMERCIO",
    "BANCO DE CREDITO",
    "BANCO FALABELLA",
    "BANCO GNB",
    "BANCO PICHINCHA",
    "BANCO RIPLEY",
    "BBVA",
    "BN. SANTANDER CONS *",
    "CITIBANK DEL PERU",
    "COMPARTAMOS BANCO",
    "INTERBANK",
    "MIBANCO",
    "NACION",
    "SANTANDER PERU",
    "SCOTIABANK PERU",
    "FINANC. PROEMPRESA",
    "FINANCIERA CONFIANZA",
    "FINANCIERA EFECTIVA",
    "FINANCIERA OH S A",
    "FINANCIERA QAPAQ",
    "FINANCIERA SURGIR",
    "MITSUI AUTO FINANCE",
    "CMAC AREQUIPA",
    "CMAC CUSCO S A",
    "CMAC DEL SANTA",
    "CMAC HUANCAYO",
    "CMAC ICA",
    "CMAC MAYNAS",
    "CMAC PAITA",
    "CMAC PIURA",
    "CMAC TACNA",
    "CMAC TRUJILLO",
    "CMCP LIMA",
    "CRAC CENCOSUD SCOTIA",
    "CRAC DEL CENTRO",
    "CRAC INCASUR",
    "CRAC LOS ANDES",
    "CRAC PRYMERA",
    "ALTERNATIVA",
    "EMP.CRED.VIVELA",
    "SANTANDER CONSUMO PERU",
    "TOTAL SERVICIOS FINANCIEROS EMPRESA DE CRÉDITOS",
)

# Everything that is data, or that generates data. A generator holding a
# real name is as bad as a fixture holding one — it puts the name back on
# the next regeneration, which is exactly how B2 happened.
SCANNED_GLOBS: tuple[str, ...] = (
    "app/src/lib/*.json",
    "app/src/lib/source-samples.ts",
    "data/*",
    "data/**/*",
    "api/sbs_api/agents/fixtures/**/*.json",
    "standards-pack/examples/*.json",
    "scripts/build_rr1_fixture.py",
    "scripts/build_journey_fixtures.py",
    "scripts/generate-synthetic-corpus.py",
    "scripts/seed_golden_complaint.py",
    "scripts/dev-seed.sql",
)

# This file necessarily contains every banned name — a denylist has to.
# It holds names only: no volume, amount or narrative is attributed to any
# of them anywhere in this file, which is the difference between a gate and
# the thing it guards against.
EXEMPT_PATHS: frozenset[str] = frozenset({
    "tests/cleanup/test_no_real_entities.py",
})


def _tracked_files() -> list[pathlib.Path]:
    """Files tracked at HEAD that match SCANNED_GLOBS.

    ``git ls-files`` rather than a filesystem walk: what matters is what
    gets published, and an untracked local scratch file does not.
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--", *SCANNED_GLOBS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"git ls-files failed ({proc.returncode}): {proc.stderr.strip()}. "
        "This gate cannot run without git and must not pass silently."
    )
    return [
        REPO_ROOT / name
        for name in proc.stdout.split("\0")
        if name and name not in EXEMPT_PATHS
    ]


def _brand_hits(text: str) -> list[str]:
    return [
        brand for brand in BRAND_NAMES
        if re.search(rf"\b{re.escape(brand)}\b", text, re.IGNORECASE)
    ]


def _label_hits(text: str) -> list[str]:
    return [label for label in WORKBOOK_LABELS if label in text]


def _scan(paths: list[pathlib.Path]) -> list[str]:
    """Every ``path: name`` offence across ``paths``.

    Split out from the gates below so a negative control can drive the
    whole read-and-match path over a planted file, rather than only
    testing the matchers in isolation.
    """
    offences: list[str] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: nothing greppable in it
        try:
            name = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            name = path.name
        for hit in _brand_hits(text) + _label_hits(text):
            offences.append(f"{name}: {hit}")
    return offences


# ---------------------------------------------------------------------------
# Negative controls — run first, because a containment gate that cannot
# fail is worse than no gate. These prove the matchers work and that the
# scan is looking at something.
# ---------------------------------------------------------------------------


def _planted_row(name: str) -> str:
    """A fixture row shaped like the real thing, with invented numbers.

    The numbers matter: quoting the real monthly volumes here, even as
    test data, would put the third-party statistics this gate exists to
    remove back into a tracked file.
    """
    return f'{{"label": "{name}", "values": [11, 22, 33], "total": 66}}'


@pytest.mark.parametrize("brand", BRAND_NAMES)
def test_control_every_brand_is_detectable(brand: str):
    """Each brand is found when planted, in three casings."""
    for variant in (brand, brand.upper(), brand.lower()):
        assert brand in _brand_hits(_planted_row(variant)), (
            f"{brand!r} planted as {variant!r} was not detected — the gate "
            f"would not catch it in a real fixture"
        )


@pytest.mark.parametrize("label", WORKBOOK_LABELS)
def test_control_every_workbook_label_is_detectable(label: str):
    """Each workbook label is found when planted in the shape it would return in."""
    assert label in _label_hits(_planted_row(label)), (
        f"{label!r} planted verbatim was not detected — the gate would not "
        f"catch a re-extracted workbook row"
    )


def test_control_scan_reports_a_planted_file(tmp_path: pathlib.Path):
    """The whole read-and-match path fails on a planted fixture.

    The matcher controls above prove the patterns work. This proves the
    gate around them does: a file on disk containing a banned name comes
    back as an offence, with the name in the message.
    """
    planted = tmp_path / "rr1-2025.json"
    planted.write_text(
        "[\n  " + _planted_row("BANCO DE CREDITO") + ",\n  "
        + _planted_row("Interbank") + "\n]\n",
        encoding="utf-8",
    )
    offences = _scan([planted])
    assert offences, "a planted fixture produced no offence — the gate is inert"
    assert any("BANCO DE CREDITO" in o for o in offences)
    assert any("Interbank" in o for o in offences)


def test_control_scan_is_clean_on_a_fictional_file(tmp_path: pathlib.Path):
    """And passes a file naming only the fictional institutions."""
    clean = tmp_path / "rr1-2025.json"
    clean.write_text(
        "[\n  " + _planted_row("Banco Nuevo Horizonte del Perú") + ",\n  "
        + _planted_row("Caja Municipal Vista Alegre") + "\n]\n",
        encoding="utf-8",
    )
    assert _scan([clean]) == []


def test_control_generic_spanish_does_not_trip_the_gate():
    """The gate must not fire on the words it deliberately matches narrowly.

    ``ALTERNATIVA`` and ``NACION`` are institution labels and also ordinary
    Spanish. Segment classes like ``Banco`` and ``Caja municipal`` appear
    all over the generated fixtures. If any of these tripped the gate it
    would be turned off within a week, which is the real failure mode.
    """
    innocuous = (
        "El cliente solicitó una alternativa de pago y presentó su "
        "Documento Nacional de Identidad en la agencia. "
        '{"label": "Banco", "total": 2385002}, '
        '{"label": "Caja municipal", "total": 39775}, '
        '{"label": "Caja Municipal Vista Alegre", "total": 2966}, '
        '{"label": "Banco Nuevo Horizonte del Perú", "total": 345348}, '
        '{"label": "Financiera Surandina del Perú", "total": 4200}, '
        '{"label": "Empresa de Crédito Kuska", "total": 339}'
    )
    assert _brand_hits(innocuous) == []
    assert _label_hits(innocuous) == []


def test_control_scan_scope_is_populated():
    """The scan must actually reach the two fixtures this gate exists for.

    A glob that matches nothing passes every assertion below. This is the
    check that the pass is not vacuous.
    """
    scanned = {p.relative_to(REPO_ROOT).as_posix() for p in _tracked_files()}
    for required in (
        "app/src/lib/rr1-2025.json",
        "app/src/lib/journey-emails.json",
        "scripts/build_rr1_fixture.py",
        "scripts/build_journey_fixtures.py",
        "scripts/dev-seed.sql",
        "data/synthetic-corpus-templates.yaml",
    ):
        assert required in scanned, f"{required} is not being scanned"
    assert len(scanned) >= 10, f"only {len(scanned)} files in scope"


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------


def test_no_real_institution_is_named_in_committed_data():
    """The gate. No banned name in any committed fixture or generator.

    A failure here is B1 or B2 regressing: real supervisory statistics or
    real complaint narratives attributed to real institutions, in a
    repository whose NOTICE says there are none.
    """
    offences = _scan(_tracked_files())
    assert not offences, (
        "Real financial institutions are named in committed data. "
        "DATA_PROVENANCE.md and NOTICE both say none are — one of those "
        "claims is now false. Regenerate the fixture rather than editing "
        "it:\n  " + "\n  ".join(offences)
    )


def test_rr1_fixture_names_only_fictional_institutions():
    """Every Empresa entity row is one of the generator's invented names.

    Stronger than the absence checks above, and the reason it can be:
    build_rr1_fixture.py holds the closed set of names it is allowed to
    emit, so the fixture can be checked against it rather than against a
    denylist of everything it must not say.
    """
    import json
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from build_rr1_fixture import ALL_FICTIONAL_INSTITUTIONS, SEGMENTS

    fixture = json.loads(
        (REPO_ROOT / "app" / "src" / "lib" / "rr1-2025.json").read_text(
            encoding="utf-8"
        )
    )
    headings = {segment[0] for segment in SEGMENTS}
    allowed = set(ALL_FICTIONAL_INSTITUTIONS) | headings

    labels = [row["label"] for row in fixture["sheets"]["Empresa"]["rows"]]
    unexpected = sorted(set(labels) - allowed)
    assert not unexpected, f"Empresa rows not from the fictional pool: {unexpected}"
    assert len(labels) == len(ALL_FICTIONAL_INSTITUTIONS) + len(headings)


def test_journey_fixture_names_only_fictional_institutions():
    """No entity outside the generator's invented set appears in the fixture.

    Covers the narrative bodies, which is where B2 lived: the structured
    EMPRESA column had been genericised and the prose had not.
    """
    import json
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from build_journey_fixtures import ENTITIES

    rows = json.loads(
        (REPO_ROOT / "app" / "src" / "lib" / "journey-emails.json").read_text(
            encoding="utf-8"
        )
    )
    blob = json.dumps(rows, ensure_ascii=False)
    assert _brand_hits(blob) == []
    assert _label_hits(blob) == []
    # Whatever institutions the prose does name must come from the pool.
    for entity in ENTITIES:
        assert _brand_hits(entity) == [], f"{entity!r} is not fictional"
        assert _label_hits(entity) == [], f"{entity!r} is not fictional"
