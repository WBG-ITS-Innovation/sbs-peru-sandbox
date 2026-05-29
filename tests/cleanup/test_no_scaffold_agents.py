"""Taxonomy-harmonizer removal; cross-source-correlator retained (P-RESHAPE-9).

The taxonomy-harmonizer ReplayProvider scaffold agent is gone from
active code paths: no caller routes it and no consumer reads its
output. The cross-source-correlator scaffold is DELIBERATELY KEPT —
it is load-bearing, not dead: its replayed output feeds the cockpit
cross-source strip (``cockpit/builder.py``) and the approval bundle
(``approvals/builder.py``). The unified agent registry holds exactly
the six real cockpit agents.
"""

from __future__ import annotations

import importlib
import pathlib

from sbs_api.agents.registry import AGENT_REGISTRY

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / "api" / "sbs_api" / "agents"
REPLAY_DIR = AGENTS_DIR / "fixtures" / "replay"


def test_taxonomy_harmonizer_file_removed():
    assert not (AGENTS_DIR / "taxonomy_harmonizer.py").exists(), (
        "taxonomy_harmonizer.py should be removed"
    )


def test_taxonomy_harmonizer_replay_fixtures_removed():
    assert not (REPLAY_DIR / "taxonomy-harmonizer").exists(), (
        "replay fixture dir taxonomy-harmonizer should be gone"
    )


def test_cross_source_correlator_retained():
    """cross-source-correlator is intentionally kept — its output feeds the
    cockpit cross-source strip and the approval bundle, so it is
    load-bearing rather than dead scaffold."""
    assert (AGENTS_DIR / "cross_source_correlator.py").exists(), (
        "cross_source_correlator.py is load-bearing and must be retained"
    )
    mod = importlib.import_module("sbs_api.agents.cross_source_correlator")
    assert hasattr(mod, "run_cross_source_correlator")


def test_orchestrator_does_not_route_taxonomy_harmonizer():
    src = (AGENTS_DIR / "orchestrator.py").read_text()
    assert "taxonomy_harmonizer" not in src
    assert "run_taxonomy_harmonizer" not in src


def test_registry_has_exactly_six_agents():
    assert len(AGENT_REGISTRY) == 6
    assert set(AGENT_REGISTRY) == {
        "divalevale",
        "reclamito",
        "lupaman",
        "triage",
        "investigation",
        "insight-chatbot",
    }


def test_replay_provider_class_still_exists():
    """ReplayProvider remains a valid testing primitive — only the
    taxonomy-harmonizer scaffold that used it for demo output was removed."""
    from sbs_api.agents.providers.replay import ReplayProvider  # noqa: F401
