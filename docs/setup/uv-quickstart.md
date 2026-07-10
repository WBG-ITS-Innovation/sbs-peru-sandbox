# uv quickstart

This is the short tour for getting `uv` running on a fresh machine and using it day-to-day in this repo. For the full design rationale, see [ADR 0021 (package manager: uv)](../adr/0021-package-manager-uv.md), [ADR 0022 (Python version: 3.12)](../adr/0022-python-version-3-12.md), and [ADR 0023 (workspace layout)](../adr/0023-workspace-layout-uv-members.md).

## What uv is

`uv` is a Python package manager and project tool from Astral. In this repo it replaces `pip + pip-tools + venv + virtualenv` with a single binary. It reads `pyproject.toml`, writes and reads `uv.lock`, manages the `.venv` directory for you, and can install Python interpreters on its own without a separate version manager.

## Install paths

Choose the first path that works on your machine. Document which path you took in the session journal (helps the next contributor).

1. **Homebrew (preferred on macOS, when available).** `brew install uv`. Cleanest path under Zscaler because Homebrew handles its own certificate chain. Requires admin to install Homebrew if it is not already present.
2. **Astral curl installer.** `curl -LsSf https://astral.sh/uv/install.sh | sh`. Downloads a signed binary. If Zscaler interrupts signature verification, set `CURL_CA_BUNDLE` and `REQUESTS_CA_BUNDLE` to the WBG CA bundle and retry.
3. **pipx.** `pipx install uv`. Requires `pipx` itself to be installed first; not faster than the curl installer in practice.
4. **`pip install uv` against the system Python.** `python3 -m pip install --user uv`. This is the path the maintainer took on the WBG-issued laptop where Prompt 3 was developed: Homebrew required admin access that was not available at the time, and the curl installer was not attempted because `pip install` worked on the first try. The resulting binary lives under `~/.local/bin/`; if that directory is not on your `PATH`, either add it or invoke uv by full path (`~/.local/bin/uv`). `uv` itself does not need to be on `PATH` for `uv run` to work once a project is initialised, but the install step needs `uv` to be invokable.

After install, confirm with `uv --version`. The repo was developed against `uv 0.11.14`; older versions may not understand the lockfile format and will tell you so on first `uv sync`.

### PATH note

`uv python install 3.12` installs the managed interpreter under `~/.local/share/uv/python/` and prints a warning that `~/.local/bin` is not on `PATH`. The warning is cosmetic for our workflow: `uv run` and `uv sync` discover managed interpreters via `uv python find`, not via `PATH`. You only need `~/.local/bin` on `PATH` if you want to invoke `python3.12` directly outside of `uv run`.

## The four commands

These are the commands you will use day-to-day.

```bash
uv sync           # Create or update .venv from pyproject.toml + uv.lock. Run after every pull.
uv run <cmd>      # Run a command in the project's .venv. e.g. `uv run pytest tests/`.
uv add <pkg>      # Add a dependency. Edits pyproject.toml and uv.lock.
uv lock           # Refresh the lockfile without installing. Rarely needed standalone.
```

Two more that come up:

- `uv python install 3.12` — install a uv-managed CPython 3.12. Use the first time you set up the repo if you do not have a 3.12 interpreter.
- `uv export --format requirements-txt > requirements.txt` — produce a pinned `requirements.txt` from the lockfile. Used inside container builds, where the runtime image installs via `pip` against the exported file instead of carrying uv.

## Workspace layout

The repo is a single uv workspace:

```
sbs-suptech-prototype/
├── pyproject.toml          # workspace root + dev dependency group
├── uv.lock                 # shared lockfile, committed
├── .python-version         # "3.12" — uv reads this to select the interpreter
├── api/        ← member    # FastAPI service surface (scaffolded in Part 2)
├── agents/     ← member    # LangGraph agent layer (scaffolded in Part 6)
├── tools/      ← member    # MCP tool servers (scaffolded in Part 5)
├── sdk/        ← member    # generated client SDKs (scaffolded in Part 3)
├── frontend/   (not a member; JS/TS toolchain, Part 8)
└── infra/      (not a member; Terraform + Helm, Part 9)
```

Each member has its own `pyproject.toml` for package-local dependencies; the root holds shared dev dependencies (the harness scripts in `scripts/` and the regression tests in `tests/`). `uv.lock` at the root is shared by every member, so transitive dependencies resolve once and identically across the workspace.

## Working behind Zscaler

If `uv sync` or `uv python install 3.12` fails with a TLS error, the WBG CA bundle is not visible to uv. The short version: set `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` to the WBG bundle, retry. Both `uv` and its child processes (pytest included) inherit those variables, so one fix covers the whole tree.

The end-to-end verification for cert inheritance is: `uv run python -c 'import urllib.request as u; print(u.urlopen("https://pypi.org").status)'`. If that prints 200, both `uv` itself and its Python subprocesses are correctly routed through Zscaler. The maintainer's first run on the WBG laptop completed in 53.8 seconds without any explicit CA-bundle configuration; the bundle was already in the system trust store. Your mileage may vary depending on how your laptop was provisioned.

## Common errors

- **`error: No interpreter found for Python 3.12`** — run `uv python install 3.12`.
- **`error: The lockfile at uv.lock needs to be updated`** — someone changed `pyproject.toml` without running `uv lock`. Run `uv sync` (which re-locks if needed) and commit the diff.
- **`error: requires-python = '>=3.12,<3.13' is incompatible with X.Y.Z`** — your local interpreter is not 3.12. Either install one with `uv python install 3.12` or let uv pick its managed interpreter automatically.
- **`error: CERTIFICATE_VERIFY_FAILED` (during `uv sync` against PyPI)** — Zscaler is intercepting and uv cannot see the WBG CA; set the variables above.
