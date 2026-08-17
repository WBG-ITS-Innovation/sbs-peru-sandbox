// SPDX-License-Identifier: Apache-2.0
// Resolves the Python interpreter the cockpit's server-side routes shell
// out to.
//
// Several BFF routes spawn a script under scripts/ rather than bundling
// Postgres drivers into the Next.js runtime — see the comments on the
// individual routes. They each hard-coded `<repo>/.venv/bin/python`,
// which assumes one specific virtualenv layout in one specific place and
// fails with a bare ENOENT anywhere else: a uv-managed env outside the
// repo, a conda env, a container image with a system Python, or Windows
// (where the binary is `Scripts/python.exe`).
//
// Set SBS_PYTHON_BIN to override. The previous path stays the fallback,
// so an existing checkout keeps working with no configuration.

import path from 'node:path';

/** Repo root, resolved from the Next.js cwd, which is `app/`. */
export const REPO_ROOT = path.resolve(process.cwd(), '..');

/** Absolute path to the repo's conventional virtualenv interpreter. */
export const DEFAULT_PYTHON_BIN = path.join(REPO_ROOT, '.venv', 'bin', 'python');

/**
 * The interpreter to spawn: `SBS_PYTHON_BIN` when set and non-empty,
 * otherwise `<repo>/.venv/bin/python`.
 *
 * Read at call time rather than module load so a dev server picks up an
 * env change on the next request instead of needing a restart.
 */
export function pythonBin(): string {
  const configured = process.env.SBS_PYTHON_BIN?.trim();
  return configured || DEFAULT_PYTHON_BIN;
}
