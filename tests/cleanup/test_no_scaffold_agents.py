"""Scaffold-agent removal (P-RESHAPE-9).

The taxonomy-harmonizer and cross-source-correlator ReplayProvider
scaffold agents are gone from active code paths; the unified agent
registry holds exactly the six real cockpit agents.
"""

from __future__ import annotations

import pathlib

from sbs_api.agents.registry import AGENT_REGISTRY

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = REPO_ROOT / "api" / "sbs_api" / "agents"
REPLAY_DIR = AGENTS_DIR / "fixtures" / "replay"


def test_scaffold_agent_files_removed():
    for name in ("cross_source_correlator.py", "taxonomy_harmonizer.py"):
        assert not (AGENTS_DIR / name).exists(), f"{name} should be removed"


def test_scaffold_replay_fixtures_removed():
    for name in ("cross-source-correlator", "taxonomy-harmonizer"):
        assert not (REPLAY_DIR / name).exists(), f"replay fixture {name} should be gone"


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
    """ReplayProvider remains a valid testing primitive — only the scaffold
    agents that used it for demo output were removed."""
    from sbs_api.agents.providers.replay import ReplayProvider  # noqa: F401


def test_orchestrator_does_not_route_scaffold_agents():
    src = (AGENTS_DIR / "orchestrator.py").read_text()
    assert "run_cross_source_correlator" not in src
    assert "include_scaffolded" not in src
