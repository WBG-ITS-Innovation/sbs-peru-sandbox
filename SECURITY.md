# Security policy

This repository is a synthetic-data sandbox: it contains no production data and no personally identifiable information. The platform it prefigures is designed for regulator-grade deployments, so security findings are taken seriously, including in tooling and CI.

## Reporting a vulnerability

**Do not** open a public GitHub issue for a security vulnerability.

Use GitHub's **private vulnerability reporting** on this repository (Security tab → "Report a vulnerability"). If that is unavailable, email **omakhlouk@worldbank.org** with the repository name, a description, and steps to reproduce.

## Disclosure window

We ask for **coordinated disclosure** on the following timeline:

| Stage | Target |
|---|---|
| Acknowledgement of your report | 5 business days |
| Initial assessment and severity triage | 10 business days |
| Fix or documented mitigation for High/Critical findings | 60 days from acknowledgement |
| Fix or documented mitigation for Medium/Low findings | 90 days from acknowledgement |
| Public disclosure | After a fix ships, or 90 days from acknowledgement, whichever comes first |

If a fix will take longer than the window, we will tell you before it expires and agree an extension rather than let the date pass silently. If you believe a finding is being mishandled, say so in the report thread — we would rather hear it from you than read it elsewhere.

We do not operate a bug bounty. We do credit reporters in the release notes unless you ask us not to.

## Scope

In scope: the API (`api/`), web app (`app/`), agents (`agents/`), SDK helpers (`sdk-helpers/`), standards-pack tooling, and CI workflows. Out of scope: vulnerabilities requiring a compromised local development environment, and findings in the synthetic data itself.

Note that this repository is a reference implementation. Deployment-time hardening — certificates from a real CA, a secrets manager, network placement of the internal API — is the operator's responsibility and is enumerated in [docs/OPERATOR-CHECKLIST.md](docs/OPERATOR-CHECKLIST.md). A report that a default configuration is insecure for production is in scope only if the default is not already documented as sandbox-only there.

## Supported versions

This is a prototype under active development. `main` is the release line, and only the latest commit on `main` receives security fixes.

| Version | Supported |
|---|---|
| `main` (latest commit) | ✅ Yes |
| `0.1.0-handover` and earlier tags | ❌ No — upgrade to `main` |
| Feature, `part-NN/*`, and backup branches | ❌ No |
| Forks | ❌ No — but we will still take the report, and you should tell your own users |

There are no long-term support branches and no backports. If you are running a fork in production, track `main` and re-apply your changes; see [CHANGELOG.md](CHANGELOG.md) for what moved between releases.
