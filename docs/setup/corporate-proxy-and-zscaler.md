# Working behind WBG networking (Zscaler and the corporate CA bundle)

**DRAFT — best-effort until verified by a colleague on a clean machine.** The instructions below were assembled from the symptoms seen during Prompt 1 closeout and from common Zscaler troubleshooting. If you run through them on a fresh setup, please correct anything that does not match what you actually had to do and open a PR. This document graduates from DRAFT once that round-trip happens.

## What this document covers

When a contributor on a WBG-issued laptop tries to run `git push`, `pip install`, `npm install`, `gh pr create`, or `scripts/cross_review.py`, they may see one of these errors:

| Error fragment | What is happening |
| --- | --- |
| `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` | A Node-based tool (npm, the `gh` CLI on some builds) does not trust the certificate Zscaler is presenting. |
| `CERTIFICATE_VERIFY_FAILED` | Python (pip, requests, the openai SDK, `scripts/cross_review.py`) does not trust the same certificate. |
| `fatal: unable to access … SSL certificate problem` | Git itself does not trust it. |
| `tls: failed to verify certificate` | A Go binary (some `gh` builds, gitleaks) does not trust it. |

The root cause is the same in every case: the WBG network terminates TLS at Zscaler and re-signs traffic with an internal certificate authority. Tools that ship their own CA bundle (most of them) reject the re-signed cert because they have never heard of the WBG CA. The fix is to point each tool at a copy of the WBG-issued CA bundle.

## Where to get the WBG CA bundle

WBG ITS distributes the bundle through internal channels. Ask:

1. The WBG ITS helpdesk, or
2. A colleague who already has a working setup.

The bundle is usually a `.pem` or `.crt` file containing one or more certificates concatenated. Save it somewhere stable on your machine — `~/certs/corp-ca-bundle.pem` is the convention this document uses below. The actual filename is not important; what matters is that the path is exported as `$CA_BUNDLE` (see the next section) and that the file is never committed to any repository.

## Wiring each tool to the bundle

After the bundle is on disk, every tool needs to be told where to find it. Set these once per machine, ideally in `~/.zshrc` or `~/.bashrc` so they persist.

```bash
export CA_BUNDLE="$HOME/certs/corp-ca-bundle.pem"

# Python — requests, urllib3, openai SDK, pip
export REQUESTS_CA_BUNDLE="$CA_BUNDLE"
export SSL_CERT_FILE="$CA_BUNDLE"

# Node — npm, some gh builds
export NODE_EXTRA_CA_CERTS="$CA_BUNDLE"
```

Then configure each tool's own setting:

```bash
# git
git config --global http.sslCAInfo "$CA_BUNDLE"

# npm
npm config set cafile "$CA_BUNDLE"

# pip — write to ~/.config/pip/pip.conf (Linux/macOS) or %APPDATA%\pip\pip.ini (Windows)
mkdir -p ~/.config/pip
cat > ~/.config/pip/pip.conf <<EOF
[global]
cert = ${CA_BUNDLE}
EOF
```

Verify:

```bash
git ls-remote https://github.com/ >/dev/null && echo "git OK"
pip install --dry-run pip                 && echo "pip OK"
npm view npm version                       && echo "npm OK"
gh api octocat                             && echo "gh OK"
```

If any of those fail with one of the certificate errors in the table above, the corresponding tool is not picking up the bundle. Check that the env var is exported in your current shell (`echo $CA_BUNDLE`), and that the file exists and is readable.

## Symptom-to-fix table

| Symptom | Most likely cause | Fix |
| --- | --- | --- |
| `git push` fails with `SSL certificate problem` | Git not configured | `git config --global http.sslCAInfo "$CA_BUNDLE"` |
| `pip install` fails with `CERTIFICATE_VERIFY_FAILED` | pip not pointed at the bundle | Write the `pip.conf` block above, or run `pip install --cert $CA_BUNDLE …` once to confirm |
| `npm install` fails with `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` | npm not pointed at the bundle | `npm config set cafile "$CA_BUNDLE"` |
| `gh pr create` hangs or errors with TLS verification | The Go-based `gh` binary uses the system trust store | On macOS, import the bundle into the System keychain. On Linux, add to `/etc/ssl/certs/ca-certificates.crt` via `update-ca-certificates`. |
| `scripts/cross_review.py` fails with `CERTIFICATE_VERIFY_FAILED` | The openai SDK uses `requests`, which honours `REQUESTS_CA_BUNDLE` | Export `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE` (above). Restart the shell. |
| Errors only on VPN, work off VPN | Zscaler is only in the path when on the WBG network | This is expected. The fix is to configure the bundle once and forget it; the tools will use it on or off VPN without harm. |
| `gitleaks` (Go binary) fails with `tls: failed to verify certificate` | Go binaries read `SSL_CERT_FILE` and `SSL_CERT_DIR` | Confirm `SSL_CERT_FILE` is exported; some Go versions also need the cert appended to the system trust store. |

## When the cross-review script can't reach Azure

`scripts/cross_review.py` calls Azure OpenAI in the WBG ITS tenancy. If Zscaler or VPN is misbehaving and the call fails, the closeout script will hard-fail per [carry-over fix #1 from Prompt 1](../sessions/2026-05-16-prompt-01-workflow-harness.md). The sanctioned bypass is:

```bash
python3 scripts/close_prompt.py --skip-cross-review-with-reason "VPN off, no Azure access"
```

The reason string lands in the session journal. Backfill the cross-review later via `python3 scripts/cross_review.py --target <whatever>` once connectivity is restored.

## What is intentionally out of scope here

- Anything about Zscaler client installation, login, or tenant switching — that is an ITS responsibility.
- Anything about WBG-issued credentials for Azure OpenAI — those come from ITS and are documented separately in `docs/CONTRIBUTING.md` under "Cross-review backend".
- Long-term certificate rotation — when WBG ITS rotates the CA, the bundle must be re-fetched and re-pointed-at. There is no automation for that here yet.

## Open questions to clear before this document leaves DRAFT

1. Is `~/certs/corp-ca-bundle.pem` the actual ITS-recommended path, or do they distribute a different one?
2. Does the WBG-issued laptop image already configure the system trust store, making the per-tool overrides redundant?
3. Are there Windows / WSL-specific steps that should live here?
4. Is the `gitleaks` row above accurate? It was inferred, not tested.

Open a PR with the answers. This document is a contract between the maintainer and any contributor on a WBG-issued laptop, and an empty page on Day 1 of a new contributor's life is the worst outcome.
