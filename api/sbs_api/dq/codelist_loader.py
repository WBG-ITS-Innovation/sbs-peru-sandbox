"""Loader + cache for Annex 1-A code lists.

Each ``codelists/<name>.yaml`` file carries a documentation header
(``spec_source``, ``spec_file``, ``review_status``, ``applies_to``)
and either:

* a ``codes:`` list of ``{code, label, ...}`` entries, or
* an ``alias_of:`` field naming another code list whose codes apply.

The loader returns a :class:`Codelist` dataclass that exposes:

* ``codes``        — ordered list of code dicts (always non-empty).
* ``code_set``     — ``frozenset[str]`` for ``code in cl`` checks.
* ``review_status`` — ``"in_repo_spec"`` or ``"needs_review"``.

Loaded files are cached for the lifetime of the process. The cache
is keyed on the name only (not on file mtime); tests that mutate a
codelist mid-run should call :func:`reset_codelist_cache`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_CODELISTS_DIR = Path(__file__).parent / "codelists"


@dataclass(frozen=True)
class Codelist:
    """A loaded code list.

    ``codes`` is a tuple of immutable dicts (each carrying at least
    ``code`` and ``label`` keys). ``code_set`` is the membership-test
    helper. ``review_status`` lets the DQ engine flag rules that
    depend on a code list still pending SBS sign-off.
    """

    name: str
    spec_source: str
    spec_file: str
    review_status: str
    applies_to: str
    codes: tuple[dict[str, Any], ...]
    code_set: frozenset[str]

    def __contains__(self, code: str) -> bool:
        return code in self.code_set

    def submotivos_for_parent(self, parent_motivo: str) -> frozenset[str]:
        """For the ``submotivos`` list, return the set of sub-codes
        scoped to a parent motivo. Empty set if the parent is unknown.
        """

        return frozenset(
            row["code"]
            for row in self.codes
            if str(row.get("parent_motivo")) == str(parent_motivo)
        )


@lru_cache(maxsize=None)
def load_codelist(name: str) -> Codelist:
    """Load and cache a code list by file-stem name.

    Aliases (``alias_of: <other>``) are resolved transitively. The
    returned :class:`Codelist` keeps the alias's own metadata header
    (spec_source / review_status) but inherits the codes from the
    pointed-to list.
    """

    path = _CODELISTS_DIR / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"code list {name!r} not found at {path}; "
            "available: " + ", ".join(sorted(p.stem for p in _CODELISTS_DIR.glob("*.yaml")))
        )
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    if "alias_of" in payload:
        target = load_codelist(payload["alias_of"])
        return Codelist(
            name=name,
            spec_source=payload.get("spec_source", target.spec_source),
            spec_file=payload.get("spec_file", target.spec_file),
            review_status=payload.get("review_status", target.review_status),
            applies_to=payload.get("applies_to", target.applies_to),
            codes=target.codes,
            code_set=target.code_set,
        )

    codes_raw = payload.get("codes") or []
    if not codes_raw:
        raise ValueError(
            f"code list {name!r} at {path} has no ``codes:`` entries "
            "and no ``alias_of:`` target"
        )
    codes = tuple({str(k): v for k, v in row.items()} for row in codes_raw)
    code_set = frozenset(row["code"] for row in codes)

    return Codelist(
        name=name,
        spec_source=payload.get("spec_source", "<unset>"),
        spec_file=payload.get("spec_file", "<unset>"),
        review_status=payload.get("review_status", "unknown"),
        applies_to=payload.get("applies_to", "<unset>"),
        codes=codes,
        code_set=code_set,
    )


def reset_codelist_cache() -> None:
    """Drop the LRU cache. Used by tests that hot-swap a code list."""

    load_codelist.cache_clear()
