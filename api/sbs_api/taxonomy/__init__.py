"""Taxonomy normalization (P11 demo-ready overlay).

The real Annex 1-A sample carries the same logical value under several
surface forms — ``"Página web de la empresa"`` and ``"PAG. WEB DE LA
EMPRESA"`` are both the ``pagina_web`` channel. This package exposes
the canonical dictionary and the helper that maps a per-field set of
raw values onto canonical codes, plus the per-normalization audit
records the orchestrator emits.
"""

from sbs_api.taxonomy.dictionary_v1 import (
    DICTIONARY_VERSION,
    Normalization,
    NormalizationOutcome,
    normalize_payload,
)

__all__ = [
    "DICTIONARY_VERSION",
    "Normalization",
    "NormalizationOutcome",
    "normalize_payload",
]
