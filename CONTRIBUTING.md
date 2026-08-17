# Contributing

Contributions are welcome — bug reports, fixes, documentation, and design proposals alike.

## One-time setup

Prerequisites are listed in the [README](README.md#getting-started).

```bash
# Install all project + dev dependencies (uv workspace):
uv sync

# Install the pre-push hook (enforces branch naming):
bash scripts/setup_hooks.sh

# Install pre-commit hooks (gitleaks, detect-secrets, whitespace, .env guard):
uv run pre-commit install

# Copy the environment template. No cloud credentials are required for
# the test suite or for any path that leaves the agent pipeline off.
cp .env.example .env
```

## Repository layout

The Python side is a uv workspace ([ADR 0023](docs/adr/0023-workspace-layout-uv-members.md)) with members `api/`, `agents/`, `tools/`, and `sdk/`. In practice `api/` holds essentially all of the Python: the FastAPI service, and also the agent layer (`api/sbs_api/agents/`), the tool registry (`api/sbs_api/agents/tools/`), and the model providers (`api/sbs_api/agents/providers/`). The root `agents/`, `tools/`, and `sdk/` directories are reserved workspace slots that currently contain only a `pyproject.toml` — do not go looking for the agent code there. The web app lives in `app/` (Next.js); infrastructure under `infra/`; integrator-facing client helpers under `sdk-helpers/`.

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) describes how these fit together, cited to the code.

## Development loop

`make help` lists the common targets. The three-command run loop and smoke tests are in the [README](README.md#getting-started). Run the test suite with:

```bash
uv run pytest -q
```

## OpenAPI contract

The OpenAPI document at [api/openapi/sbs-api-v1.yaml](api/openapi/sbs-api-v1.yaml) is the canonical contract ([ADR 0027](docs/adr/0027-openapi-as-canonical-contract.md)); the Pydantic models implement it. After changing models, regenerate the JSON Schemas and run the match test:

```bash
bash scripts/regenerate-schemas.sh
uv run pytest tests/test_openapi_pydantic_match.py -v
```

The developer portal renders the spec via locally vendored Stoplight Elements ([ADR 0037](docs/adr/0037-developer-portal-serving-mechanism.md)): `bash scripts/serve-devportal.sh`. To update the vendored assets, follow [vendor/stoplight-elements/VENDOR.md](vendor/stoplight-elements/VENDOR.md).

## Branches, commits, PRs

- Branch names (enforced by the pre-push hook): `docs/<slug>`, `fix/<slug>`, `chore/<slug>` — or `part-NN/<slug>` for maintainer milestone work.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).
- Every PR needs green CI and one maintainer review.
- Never commit secrets. Pre-commit runs gitleaks and detect-secrets against the committed `.secrets.baseline`; if a legitimate high-entropy string trips it, refresh the baseline (`uv run detect-secrets scan > .secrets.baseline`) and include it in the PR.
- Design decisions are recorded as ADRs under [docs/adr/](docs/adr/) — open an issue with the "ADR request" template to propose one.

## Security

Never open a public issue for a vulnerability — see [SECURITY.md](SECURITY.md).
