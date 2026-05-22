"""i18n parity gate.

The Spanish dictionary (`app/src/i18n/es.json`) is canonical; English
(`en.json`) is offered via the toggle. Both must carry the same key set.
A PR that adds a key to one and not the other fails this test.

Native-speaker review of the Spanish dictionary by Luis happens
separately (WS0c); this test only enforces structural parity.
"""

from __future__ import annotations

import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ES_PATH = REPO_ROOT / "app" / "src" / "i18n" / "es.json"
EN_PATH = REPO_ROOT / "app" / "src" / "i18n" / "en.json"


def _flatten(d: dict, prefix: str = "") -> set[str]:
    """Flatten a nested dict into a set of dotted-path keys.

    Only string leaves count as keys. A non-string leaf is a contract
    violation; this function raises so the test fails loudly rather than
    silently treating an integer / array as a missing key.
    """

    keys: set[str] = set()
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            keys |= _flatten(v, path)
        elif isinstance(v, str):
            keys.add(path)
        else:
            raise AssertionError(
                f"i18n leaf at {path} must be a string, got {type(v).__name__}"
            )
    return keys


def _load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_es_and_en_dictionaries_have_identical_key_sets() -> None:
    es = _flatten(_load(ES_PATH))
    en = _flatten(_load(EN_PATH))
    missing_in_en = sorted(es - en)
    missing_in_es = sorted(en - es)
    assert not missing_in_en and not missing_in_es, (
        "i18n dictionaries drifted.\n"
        f"  keys present in es.json but not en.json ({len(missing_in_en)}): {missing_in_en}\n"
        f"  keys present in en.json but not es.json ({len(missing_in_es)}): {missing_in_es}"
    )


def test_pinned_namespaces_present_in_both_dictionaries() -> None:
    """The namespace taxonomy is pinned in app/src/i18n/README.md.

    Adding a new top-level namespace requires the README update in the
    same PR. This test catches the inverse: a workstream removing a
    namespace by accident.
    """

    pinned_namespaces = {
        "common",
        "nav",
        "auth",
        "cockpit",
        "findings",
        "approvals",
        "queue",
        "audit",
        "personas",
        "errors",
    }
    for path in (ES_PATH, EN_PATH):
        top_level = set(_load(path).keys())
        missing = pinned_namespaces - top_level
        assert not missing, (
            f"{path.name} is missing pinned namespaces: {sorted(missing)}. "
            f"If you removed a namespace intentionally, update "
            f"app/src/i18n/README.md in the same PR."
        )


def test_common_actions_namespace_carries_shared_verbs() -> None:
    """common.actions.* is the shared verb home — see app/src/i18n/README.md.

    These four verbs appear in more than one screen. A workstream that
    re-implements them per-screen is the failure mode this test catches.
    """

    required_action_keys = {
        "common.actions.approve",
        "common.actions.reject",
        "common.actions.edit",
        "common.actions.cancel",
        "common.actions.save",
        "common.actions.signout",
    }
    for path in (ES_PATH, EN_PATH):
        keys = _flatten(_load(path))
        missing = required_action_keys - keys
        assert not missing, (
            f"{path.name} is missing required common.actions.* keys: "
            f"{sorted(missing)}"
        )


def test_severity_labels_present_in_both_dictionaries() -> None:
    """The four severity bands are shared vocabulary; they live under
    common.severity.* and must exist in both dictionaries."""

    required = {
        "common.severity.low",
        "common.severity.medium",
        "common.severity.high",
        "common.severity.critical",
    }
    for path in (ES_PATH, EN_PATH):
        keys = _flatten(_load(path))
        missing = required - keys
        assert not missing, (
            f"{path.name} is missing common.severity.* keys: {sorted(missing)}"
        )
