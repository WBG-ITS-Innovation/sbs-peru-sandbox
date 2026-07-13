# Security policy

This repository is a synthetic-data sandbox: it contains no production data and no personally identifiable information. The platform it prefigures is designed for regulator-grade deployments, so security findings are taken seriously, including in tooling and CI.

## Reporting a vulnerability

**Do not** open a public GitHub issue for a security vulnerability.

Use GitHub's **private vulnerability reporting** on this repository (Security tab → "Report a vulnerability"). If that is unavailable, email **omakhlouk@worldbank.org** with the repository name, a description, and steps to reproduce.

You should receive an acknowledgement within five business days. Please allow maintainers reasonable time to remediate before public disclosure.

## Scope

In scope: the API (`api/`), web app (`app/`), agents (`agents/`), SDK helpers (`sdk-helpers/`), standards-pack tooling, and CI workflows. Out of scope: vulnerabilities requiring a compromised local development environment, and findings in the synthetic data itself.

## Supported versions

This is a prototype under active development; only the `main` branch is supported.
