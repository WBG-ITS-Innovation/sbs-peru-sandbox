#!/usr/bin/env python3
"""Cross-model review: send a target (file path, glob, or 'staged') to Azure
OpenAI (WBG ITS tenancy) for an independent critique. Output is written to
docs/reviews/.

This project uses Azure OpenAI exclusively. Personal openai.com keys are not
supported and will fail validation. WBG data-governance policy requires Azure
OpenAI for any model calls touching project content.

Usage:
    python scripts/cross_review.py --target path/to/file.py
    python scripts/cross_review.py --target 'api/**/*.py'
    python scripts/cross_review.py --target staged

Environment (all four required):
    AZURE_OPENAI_API_KEY       the WBG-issued key.
    AZURE_OPENAI_ENDPOINT      e.g. https://<resource>.openai.azure.com/
    AZURE_OPENAI_DEPLOYMENT    the deployment name (not the model id).
    AZURE_OPENAI_API_VERSION   e.g. 2024-10-21
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import pathlib
import re
import subprocess
import sys
import textwrap

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REVIEWS_DIR = REPO_ROOT / "docs" / "reviews"

REQUIRED_SECTIONS = [
    "## Summary",
    "## Disagreements with primary review",
    "## Risks not flagged elsewhere",
    "## Recommended actions",
    "## Triage",
]

SYSTEM_PROMPT = textwrap.dedent(
    """
    You are a senior engineer performing an independent cross-model code/document
    review for a regulator-grade SupTech platform (SBS Peru). The primary author
    is a solo developer assisted by Claude. Your job is to find what they and
    Claude may have missed.

    The project's north-star principles are: (1) one-command deploy, (2)
    configuration over code, (3) observability as a first-class feature, (4)
    standards over inventions plus product-grade onboarding, (5) plain-language
    explainability, (6) built on benchmarked precedent.

    Required tone: calm, senior, direct. No marketing language. No
    AI-sounding phrasing ("leverage", "robust", "seamless", etc.). Plain
    language readable by a financial regulator.

    Required output: Markdown with these exact section headers, in this order:

    ## Summary
    ## Disagreements with primary review
    ## Risks not flagged elsewhere
    ## Recommended actions
    ## Triage

    Leave the Triage section blank — the human fills it in.

    Be specific. Cite file:line where possible. Name comparators where you
    invoke "industry practice". If you cannot find substantive issues, say so
    explicitly and explain what you looked for.
    """
).strip()


def load_dotenv_if_present() -> None:
    """Load .env from the repo root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def collect_target(target: str) -> tuple[str, str]:
    """Return (combined_content, slug). Slug is used in the output filename."""
    if target == "staged":
        result = subprocess.run(
            ["git", "diff", "--staged"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        if not result.stdout.strip():
            sys.exit("No staged changes. Stage something with `git add` and try again.")
        return result.stdout, "staged-diff"

    matches = sorted(glob.glob(target, recursive=True))
    if not matches:
        path = pathlib.Path(target)
        if path.is_file():
            matches = [str(path)]
        else:
            sys.exit(f"No files matched target: {target}")

    parts: list[str] = []
    for m in matches:
        p = pathlib.Path(m)
        if not p.is_file():
            continue
        parts.append(f"=== FILE: {p.relative_to(REPO_ROOT) if p.is_absolute() else p} ===")
        try:
            parts.append(p.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            parts.append("[binary file — skipped]")
        parts.append("")
    combined = "\n".join(parts)
    slug = _slugify(target)
    return combined, slug


def _slugify(s: str) -> str:
    # Strip a trailing file extension so we don't get filenames like ".md.md".
    s = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", s)
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-").lower()
    return s[:60] or "review"


REQUIRED_AZURE_ENV_VARS = (
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
)


def check_azure_env() -> dict[str, str]:
    """Validate all four Azure OpenAI env vars are set. Fail loudly if not."""
    missing = [v for v in REQUIRED_AZURE_ENV_VARS if not os.environ.get(v)]
    if missing:
        sys.exit(
            "Azure OpenAI is required for cross-review (WBG governance — no "
            "personal openai.com keys).\n"
            f"Missing env vars: {', '.join(missing)}\n"
            "Set them in .env (see .env.example) or your shell. Endpoint and "
            "deployment name come from WBG ITS or the Azure portal."
        )
    return {v: os.environ[v] for v in REQUIRED_AZURE_ENV_VARS}


def call_azure_openai(content: str, deployment: str) -> str:
    try:
        from openai import AzureOpenAI  # type: ignore
    except ImportError:
        sys.exit(
            "openai package not installed. Run: "
            "pip install -r scripts/requirements-harness.txt"
        )

    env = check_azure_env()
    client = AzureOpenAI(
        api_key=env["AZURE_OPENAI_API_KEY"],
        api_version=env["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=env["AZURE_OPENAI_ENDPOINT"],
    )
    user_message = (
        "Review the following. Use the five required sections in the order "
        "specified by your instructions.\n\n" + content
    )

    response = client.chat.completions.create(
        model=deployment,  # Azure: deployment NAME, not OpenAI model id.
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content or ""


def enforce_sections(body: str) -> str:
    """Append any missing required section headers so the file is well-formed."""
    out = body.rstrip() + "\n"
    for header in REQUIRED_SECTIONS:
        if header not in out:
            out += f"\n{header}\n\n_Not provided by the model — please fill in or re-run._\n"
    if "## Triage" in out:
        idx = out.index("## Triage")
        after = out[idx:]
        if "TODO" not in after and "fill in" not in after.lower():
            out = out[:idx] + "## Triage\n\n_TODO: human-filled. Disposition each finding above as accept / defer / reject, with reason._\n"
    return out


def write_review(slug: str, body: str, model: str) -> pathlib.Path:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    date = dt.date.today().isoformat()
    path = REVIEWS_DIR / f"{date}-{slug}.md"
    header = textwrap.dedent(
        f"""\
        # Cross-model review — {slug}

        - **Date:** {date}
        - **Model:** {model}
        - **Target:** {slug}

        ---

        """
    )
    path.write_text(header + body, encoding="utf-8")
    return path


def main() -> int:
    load_dotenv_if_present()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        required=True,
        help="File path, glob, or the literal string 'staged'.",
    )
    parser.add_argument(
        "--deployment",
        default=os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
        help="Azure OpenAI deployment name (default: env AZURE_OPENAI_DEPLOYMENT).",
    )
    args = parser.parse_args()

    # Validate up-front so the user sees a clean error before any file I/O.
    check_azure_env()
    deployment = args.deployment or os.environ["AZURE_OPENAI_DEPLOYMENT"]

    content, slug = collect_target(args.target)
    body = call_azure_openai(content, deployment)
    body = enforce_sections(body)
    path = write_review(slug, body, deployment)
    print(str(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
