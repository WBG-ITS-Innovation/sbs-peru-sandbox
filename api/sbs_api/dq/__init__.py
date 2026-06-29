# SPDX-License-Identifier: Apache-2.0
"""Annex 1-A data-quality package.

Hosts the canonical code-list YAML files under ``codelists/`` and the
loader that reads them. The 21 new Annex 1-A DQ rules (DQ-A1A-007
through DQ-A1A-027) live in ``sbs_api.data_quality.annex_1a_rules``
so the existing ``data_quality.checks`` module continues to drive
the aggregate ``data-quality-completed`` audit event unchanged.
"""

from sbs_api.dq.codelist_loader import Codelist, load_codelist

__all__ = ["Codelist", "load_codelist"]
