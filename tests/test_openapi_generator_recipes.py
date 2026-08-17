# SPDX-License-Identifier: Apache-2.0
"""Smoke checks for the OpenAPI Generator recipes (E.2).

The recipes at ``standards-pack/recipes/openapi-generator-*.md`` are
markdown how-tos. The smoke checks here:

* verify each recipe exists and is non-empty
* verify each recipe pins the documented generator version
  (``v7.10.0``) — drift in the pin would mean institutions follow
  the docs to a different version than CI validates
* verify each recipe mentions the "wrap, never edit" pattern
* verify the Go recipe explicitly names the oneOf/anyOf/discriminator
  known issue

A full invocation of openapi-generator-cli (i.e. actually running
the docker container against the spec and asserting the output
directory's expected file presence) is a CI-only smoke check that
lives in the workflow at .github/workflows/standards-pack-validate.yml
when Docker-in-Docker is available; the local pytest run cannot
assume Docker. Both gates exercise the same scope: "can an integrator
follow the recipe and get a generated client?".
"""

from __future__ import annotations

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RECIPES_DIR = REPO_ROOT / "standards-pack" / "recipes"

GENERATOR_PIN = "openapitools/openapi-generator-cli:v7.10.0"
WRAP_PATTERN_PHRASE = "Wrap, never edit"
GO_UNION_KNOWN_ISSUE = "oneOf"


@pytest.mark.parametrize(
    "filename",
    [
        "openapi-generator-java.md",
        "openapi-generator-csharp-netcore.md",
        "openapi-generator-go.md",
    ],
)
def test_recipe_exists_and_is_non_empty(filename):
    path = RECIPES_DIR / filename
    assert path.is_file(), f"missing recipe: {path}"
    assert path.stat().st_size > 500, f"recipe is suspiciously small: {path}"


@pytest.mark.parametrize(
    "filename",
    [
        "openapi-generator-java.md",
        "openapi-generator-csharp-netcore.md",
        "openapi-generator-go.md",
    ],
)
def test_recipe_pins_generator_version_v7_10_0(filename):
    """Every recipe must pin the generator to v7.10.0 per ADR 0038."""

    text = (RECIPES_DIR / filename).read_text(encoding="utf-8")
    assert GENERATOR_PIN in text, (
        f"{filename} must pin {GENERATOR_PIN!r}; drift between the docs "
        f"and the ADR breaks the reproducibility contract"
    )


@pytest.mark.parametrize(
    "filename",
    [
        "openapi-generator-java.md",
        "openapi-generator-csharp-netcore.md",
        "openapi-generator-go.md",
    ],
)
def test_recipe_documents_wrap_never_edit_pattern(filename):
    """Each recipe must document the wrap-never-edit pattern."""

    text = (RECIPES_DIR / filename).read_text(encoding="utf-8")
    assert WRAP_PATTERN_PHRASE.lower() in text.lower(), (
        f"{filename} must document the wrap-never-edit pattern; "
        f"this is the dominant integration pain point per ADR 0038"
    )


def test_go_recipe_names_the_union_type_known_issue():
    """The Go recipe must surface the oneOf/anyOf/discriminator issue.

    ADR 0038's rationale for the Go recipe explicitly calls out the
    known issue. Removing the warning would re-introduce the
    "generated client won't compile" surprise.
    """

    text = (RECIPES_DIR / "openapi-generator-go.md").read_text(encoding="utf-8")
    assert GO_UNION_KNOWN_ISSUE in text
    assert "workaround" in text.lower()


def test_csharp_recipe_is_csharp_netcore_not_old_csharp():
    """The C# recipe must target the modern csharp-netcore generator.

    ADR 0038 names this explicitly: the older `csharp` generator
    emits materially different output; the recipe ships csharp-
    netcore only.
    """

    text = (RECIPES_DIR / "openapi-generator-csharp-netcore.md").read_text(
        encoding="utf-8"
    )
    assert "csharp-netcore" in text
    # Either explicitly named as the modern generator, or the docker
    # invocation uses `-g csharp-netcore`.
    assert "-g csharp-netcore" in text
