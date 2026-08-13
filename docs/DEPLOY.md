# Deployment

**This document is a scaffold, not a deployment guide.** No production deployment path exists yet: there is no Helm chart in this repository, and nothing below has been executed. It captures the intended structure so contributors know where deployment material belongs as it is written. Everything in the table of contents is a plan; treat it as such.

## Table of contents (intended)

1. **Overview**
   - One-paragraph description of the deployment shape (Helm chart on k8s, Postgres + Redis + vLLM as core dependencies).
   - The three target environments: dev (Docker Compose), staging (k3d / kind), prod / SBS (on-prem k8s + Terraform-managed dependencies), Azure tenancy overlay.

2. **Prerequisites**
   - Kubernetes 1.28+, Helm 3, kubectl.
   - For Azure: an AKS cluster, Azure Database for PostgreSQL Flexible Server, Azure Key Vault, ACR.
   - For bare-metal: PostgreSQL 16 with pgvector, Redis 7, a GPU-equipped node for vLLM (or CPU-only with a smaller model — see ADR for the runtime tradeoff).
   - Certificates: a CA, server cert, and client certs for each supervised institution (issued via the SBS PKI or the dev CA shipped with the repo).

3. **One-command deploy (the north-star)**
   - `helm install sbs-suptech ./charts/sbs-suptech -f values.<env>.yaml`
   - What that command does — pulls images, runs migrations, starts each service, configures OTel collector.
   - Verification: `helm test sbs-suptech`, conformance suite, sample signed request.

4. **Configuration model**
   - Single image, different config per environment. Never branch by environment in code (north-star principle 2).
   - Values file structure — top-level keys for `auth`, `ingestion`, `agents`, `observability`, `security`.
   - Secret references: external secret operator pulls from Key Vault (Azure) or a sealed-secret bundle (bare-metal).

5. **Network model**
   - Inbound: mTLS terminator (Envoy or nginx with cert validation) on a public endpoint for Tier 1, a separate endpoint for Tier 2 batch uploads.
   - Internal: service-to-service mTLS via the platform's service mesh (Linkerd / Istio — ADR pending).
   - Egress: webhook callbacks to supervised institutions, signed.

6. **Migrations and seed data**
   - Alembic migrations run as a pre-install hook. Idempotent.
   - Taxonomy YAML is loaded at startup; a missing taxonomy fails the readiness probe deliberately.
   - Optional seed data: synthetic dataset for sandbox environments only — never in prod.

7. **Observability**
   - OTel collector, Prometheus, Grafana, Loki as core dependencies.
   - Dashboards: ingestion (per-institution and global), agent pipeline (per-agent latency / success), API SLOs.
   - Alerts: ingestion stalled, validator failure rate, signing failure rate, queue depth, model drift.

8. **Disaster recovery**
   - RPO / RTO targets (illustrative until measured).
   - Backup procedure: continuous WAL archiving for Postgres, periodic Redis snapshots, MLflow artifact store backup.
   - Restore drill: scripted, evidence captured in a runbook.

9. **Runbooks**
   - One file per operational scenario, in a `docs/runbooks/` directory that does not exist yet.
   - Initial set: ingestion stalled, validator failing, vLLM out of memory, Postgres replication lag, cert rotation, credential leak, taxonomy version cutover.

10. **Vendor handoff package**
    - One-page architecture diagram, data-flow diagram, threat model, ADR set, runbook bundle, demo recording, vendor extension guide.

## What actually works today

Local development only — production deploy is not supported. The verified
bring-up is the three-command walk in the root
[README](../README.md#getting-started), which brings up Docker Compose,
applies migrations, seeds the dev CA and demo institutions, and runs the API
with the real auth chain. Use that rather than the commands this section used
to carry, which referenced a `api.main:app` entry point that does not exist.

For the supervisor cockpit, which additionally needs Keycloak and a second API
process, see "Run the supervisor cockpit" in the same README.
