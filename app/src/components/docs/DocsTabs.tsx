// Documentation hub — four tabs. Pure client; static content for the
// demo. Each tab is a self-contained section so the reader can copy
// the snippets straight out of the page.
//
// i18next literal-string check disabled — most strings here are
// technical code snippets, protocol field names, and bilingual labels
// that already exist in both Spanish and English in this file.
/* eslint-disable i18next/no-literal-string */

'use client';

import { useState } from 'react';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

type TabKey = 'arch' | 'api' | 'annex' | 'agents';

interface Props {
  locale: Locale;
}

export function DocsTabs({ locale }: Props) {
  const es = locale === 'es-PE';
  const [tab, setTab] = useState<TabKey>('arch');

  const tabs: Array<{ key: TabKey; label: string }> = [
    { key: 'arch', label: es ? 'Arquitectura' : 'Architecture' },
    { key: 'api', label: es ? 'API para integradores' : 'API for integrators' },
    { key: 'annex', label: es ? 'Modelo Anexo 1-A' : 'Annex 1-A model' },
    { key: 'agents', label: es ? 'Agentes y herramientas' : 'Agents & tools' },
  ];

  return (
    <div>
      <nav className="flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              tab === t.key
                ? 'border-brand-cyan text-brand-navy'
                : 'border-transparent text-fg-muted hover:text-fg',
            )}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="mt-4">
        {tab === 'arch' && <ArchTab es={es} />}
        {tab === 'api' && <ApiTab es={es} />}
        {tab === 'annex' && <AnnexTab es={es} />}
        {tab === 'agents' && <AgentsTab es={es} />}
      </div>
    </div>
  );
}

function ArchTab({ es }: { es: boolean }) {
  const steps = es
    ? [
        '1. La institución (banco) recibe el reclamo del cliente.',
        '2. Sistema interno mapea al esquema Anexo 1-A (27 campos).',
        '3. Cliente firma con mTLS, obtiene token OAuth, firma HMAC.',
        '4. POST /v1/sandbox/complaints/granular con Idempotency-Key.',
        '5. SBS valida cadena de autenticación y verifica firma.',
        '6. Tubería de ingesta: PII redactado → DQ → taxonomía → persistencia.',
        '7. Agentes ejecutan: triage → investigación → síntesis → cabina.',
        '8. Supervisor revisa hallazgo, aprueba o devuelve a la entidad.',
      ]
    : [
        '1. The institution (bank) receives the customer complaint.',
        '2. Internal system maps to the Annex 1-A schema (27 fields).',
        '3. Client presents mTLS, obtains OAuth token, computes HMAC.',
        '4. POST /v1/sandbox/complaints/granular with Idempotency-Key.',
        '5. SBS validates the auth chain and verifies the signature.',
        '6. Ingestion pipeline: PII redacted → DQ → taxonomy → persistence.',
        '7. Agents run: triage → investigation → synthesis → cockpit.',
        '8. Supervisor reviews finding, approves or sends back to entity.',
      ];
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {es ? 'Arquitectura del flujo' : 'Flow architecture'}
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <pre className="overflow-auto rounded-sbs border border-border-subtle bg-surface-subtle px-3 py-3 font-mono text-xs leading-relaxed">
{`[Cliente]
   │
   ▼
[Banco / Caja / Coopac]      ◄──── 27 campos Anexo 1-A
   │  mTLS · OAuth · HMAC
   ▼
[SBS Gateway · /v1/sandbox/complaints/granular]
   │
   ▼
[Tubería de ingesta]
   ├─ PII redactado
   ├─ Calidad de datos
   ├─ Taxonomía normalizada
   └─ Persistencia canónica
       │
       ▼
[Agentes]
   ├─ Triage   (BERT + clasificador)
   ├─ Investigación (XGBoost + SHAP + anomalía)
   └─ Síntesis (LLM · resumen ejecutivo)
       │
       ▼
[Cabina del supervisor]  ◄── SBS Conducta de Mercado
       │
       ▼
[Aprobación / devolución a la entidad]`}
          </pre>
          <ol className="space-y-1.5 text-sm leading-relaxed text-fg">
            {steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </CardBody>
      </Card>
    </div>
  );
}

function ApiTab({ es }: { es: boolean }) {
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            cURL · POST /v1/sandbox/complaints/granular
          </CardTitle>
        </CardHeader>
        <CardBody>
          <CodeBlock>
{`curl -sS -X POST https://sbs.gob.pe/v1/sandbox/complaints/granular \\
  --cert dev-ca/banco-demo-001.pem \\
  --key  dev-ca/banco-demo-001-key.pem \\
  -H "Authorization: Bearer $OAUTH_TOKEN" \\
  -H "Content-Type: application/json" \\
  -H "X-SBS-Timestamp: $TIMESTAMP" \\
  -H "X-SBS-Signature: $SIGNATURE" \\
  -H "X-SBS-Institution-Id: SBS-001234" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -d @complaint.json`}
          </CodeBlock>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Python · requests</CardTitle>
        </CardHeader>
        <CardBody>
          <CodeBlock>
{`import httpx, hashlib, hmac, base64, json, uuid
from datetime import datetime, timezone

client = httpx.Client(
    cert=("dev-ca/banco-demo-001.pem", "dev-ca/banco-demo-001-key.pem"),
    verify="dev-ca/ca.pem",
)
body  = json.dumps(payload, separators=(",", ":")).encode()
ts    = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
canon = "\\n".join(["POST", "/v1/sandbox/complaints/granular",
                    "sbs.gob.pe", ts,
                    hashlib.sha256(body).hexdigest(),
                    "SBS-001234"]).encode()
sig   = "hmac-sha256-v1=" + base64.b64encode(
    hmac.new(bytes.fromhex(secret_hex), canon, hashlib.sha256).digest()
).decode()

r = client.post(
    "https://sbs.gob.pe/v1/sandbox/complaints/granular",
    content=body,
    headers={
        "Authorization": f"Bearer {token}",
        "X-SBS-Timestamp": ts,
        "X-SBS-Signature": sig,
        "X-SBS-Institution-Id": "SBS-001234",
        "Idempotency-Key": uuid.uuid4().hex,
        "Content-Type": "application/json",
    },
)`}
          </CodeBlock>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            OAuth 2.0 client_credentials
          </CardTitle>
        </CardHeader>
        <CardBody>
          <CodeBlock>
{`curl -sS -X POST https://sbs.gob.pe/v1/oauth/token \\
  --cert dev-ca/banco-demo-001.pem \\
  --key  dev-ca/banco-demo-001-key.pem \\
  -u "banco-demo-001:$CLIENT_SECRET" \\
  -d "grant_type=client_credentials&scope=complaints:write complaints:read"

# → { "access_token": "eyJhbGc...", "scope": "complaints:write complaints:read",
#     "token_type": "Bearer", "expires_in": 600 }`}
          </CodeBlock>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">HMAC SHA-256 — canonical request</CardTitle>
        </CardHeader>
        <CardBody>
          <CodeBlock>
{`# Canonical request (newline-joined):
METHOD          POST
TARGET          /v1/sandbox/complaints/granular
HOST            sbs.gob.pe
TIMESTAMP       2026-05-27T11:50:45.381891Z
BODY_SHA256     3b5e...   # hex of sha256(body bytes)
INSTITUTION_ID  SBS-001234

# Signature header:
X-SBS-Signature: hmac-sha256-v1=<base64(HMAC_SHA256(secret, canonical))>`}
          </CodeBlock>
        </CardBody>
      </Card>
    </div>
  );
}

function AnnexTab({ es }: { es: boolean }) {
  const fields: Array<{ key: string; type: string; desc_es: string; desc_en: string; req: boolean }> = [
    { key: 'COD_REC', type: 'string', desc_es: 'Código del reclamo (institución)', desc_en: 'Complaint code (institution)', req: true },
    { key: 'TID_CLI', type: 'string', desc_es: 'Tipo de documento de identidad', desc_en: 'Document type', req: true },
    { key: 'NRO_CLI', type: 'string', desc_es: 'Número de documento', desc_en: 'Document number', req: true },
    { key: 'NCL_CLI', type: 'string', desc_es: 'Nombre del cliente', desc_en: 'Customer name', req: true },
    { key: 'COD_CLI', type: 'string', desc_es: 'Código de cliente', desc_en: 'Customer code', req: false },
    { key: 'FEC_ING', type: 'date', desc_es: 'Fecha de ingreso', desc_en: 'Date received', req: true },
    { key: 'CNL_ING', type: 'enum', desc_es: 'Canal de ingreso (Anexo A)', desc_en: 'Channel of intake (Annex A)', req: true },
    { key: 'CNL_OPE', type: 'enum', desc_es: 'Canal de la operación', desc_en: 'Operation channel', req: false },
    { key: 'FEC_AMP', type: 'date', desc_es: 'Fecha de ampliación', desc_en: 'Extension date', req: false },
    { key: 'CNL_AMP', type: 'enum', desc_es: 'Canal de ampliación', desc_en: 'Extension channel', req: false },
    { key: 'FEC_RES', type: 'date', desc_es: 'Fecha de resolución', desc_en: 'Resolution date', req: false },
    { key: 'CNL_PAC', type: 'enum', desc_es: 'Canal de pago al cliente', desc_en: 'Payment-to-customer channel', req: false },
    { key: 'UBI_REC', type: 'ubigeo', desc_es: 'Ubigeo (INEI, 6 dígitos)', desc_en: 'Ubigeo (INEI, 6 digits)', req: false },
    { key: 'PRD_SBS', type: 'enum', desc_es: 'Producto SBS (Anexo B)', desc_en: 'SBS product (Annex B)', req: true },
    { key: 'MOT_SBS', type: 'enum', desc_es: 'Motivo SBS (Anexo C)', desc_en: 'SBS motive (Annex C)', req: true },
    { key: 'SUB_SBS', type: 'enum', desc_es: 'Submotivo SBS (Anexo D)', desc_en: 'SBS submotive (Annex D)', req: false },
    { key: 'DET_REC', type: 'text', desc_es: 'Detalle del reclamo (narrativa)', desc_en: 'Complaint detail (narrative)', req: true },
    { key: 'TIP_RES', type: 'enum', desc_es: 'Tipo de resolución', desc_en: 'Resolution type', req: false },
    { key: 'DET_RES', type: 'text', desc_es: 'Detalle de la resolución', desc_en: 'Resolution detail', req: false },
    { key: 'PRD_EMP', type: 'string', desc_es: 'Producto interno de la empresa', desc_en: 'Internal product code', req: false },
    { key: 'EST_REC', type: 'enum', desc_es: 'Estado del reclamo (pendiente/atendido/anulado)', desc_en: 'Status (pending/resolved/annulled)', req: true },
    { key: 'COD_PRV', type: 'string', desc_es: 'Código del reclamo previo (si aplica)', desc_en: 'Previous complaint code (if any)', req: false },
    { key: 'BAN_SEG', type: 'bool', desc_es: 'Es operación de bancaseguros', desc_en: 'Bancassurance operation', req: false },
    { key: 'PRD_SBS_SEG', type: 'enum', desc_es: 'Producto SBS bancaseguros', desc_en: 'SBS bancassurance product', req: false },
    { key: 'MOT_SBS_SEG', type: 'enum', desc_es: 'Motivo SBS bancaseguros', desc_en: 'SBS bancassurance motive', req: false },
    { key: 'SUB_SBS_SEG', type: 'enum', desc_es: 'Submotivo SBS bancaseguros', desc_en: 'SBS bancassurance submotive', req: false },
    { key: 'MNT_PEN_REC', type: 'decimal', desc_es: 'Monto pendiente en PEN', desc_en: 'Pending amount in PEN', req: false },
    { key: 'EMPRESA', type: 'string', desc_es: 'Entidad reportante', desc_en: 'Reporting entity', req: true },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {es ? 'Anexo 1-A · Res. SBS 4036-2022 · 27 campos' : 'Annex 1-A · Res. SBS 4036-2022 · 27 fields'}
        </CardTitle>
      </CardHeader>
      <CardBody>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="border-b border-border bg-surface-subtle text-fg-muted">
              <tr>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">Campo</th>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">Tipo</th>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">
                  {es ? 'Descripción' : 'Description'}
                </th>
                <th className="px-2 py-1.5 text-center font-mono uppercase tracking-wide">
                  {es ? 'Obligatorio' : 'Required'}
                </th>
              </tr>
            </thead>
            <tbody>
              {fields.map((f) => (
                <tr key={f.key} className="border-b border-border-subtle">
                  <td className="px-2 py-1.5 font-mono font-semibold text-brand-navy">{f.key}</td>
                  <td className="px-2 py-1.5 font-mono text-fg-muted">{f.type}</td>
                  <td className="px-2 py-1.5 text-fg">{es ? f.desc_es : f.desc_en}</td>
                  <td className="px-2 py-1.5 text-center">
                    {f.req ? (
                      <span className="rounded-sm bg-status-resolved-bg px-1.5 py-0.5 font-mono text-2xs text-status-resolved-fg">
                        sí
                      </span>
                    ) : (
                      <span className="font-mono text-2xs text-fg-muted">opcional</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardBody>
    </Card>
  );
}

function AgentsTab({ es }: { es: boolean }) {
  const agents = [
    {
      name: 'triage',
      ver: '0.1.0',
      mode: 'LIVE',
      desc_es: 'Clasifica el reclamo con BERT y recomienda severidad inicial.',
      desc_en: 'Classifies the complaint with BERT and recommends initial severity.',
      tools: ['bert_classifier'],
    },
    {
      name: 'investigation',
      ver: '0.1.0',
      mode: 'LIVE',
      desc_es: 'Atribución de features (XGBoost + SHAP), anomalía compuesta, búsqueda de reclamos similares y borrador de narrativa.',
      desc_en: 'Feature attribution (XGBoost + SHAP), composite anomaly, similar-complaint search, narrative draft.',
      tools: ['rank_features', 'anomaly_detector', 'search_similar_complaints', 'draft_narrative'],
    },
    {
      name: 'synthesis',
      ver: '0.1.0',
      mode: 'LIVE',
      desc_es: 'Compone el resumen ejecutivo para la supervisora.',
      desc_en: 'Composes the executive summary for the supervisor.',
      tools: ['compose_executive_summary'],
    },
    {
      name: 'cockpit-monitor',
      ver: '0.1.0',
      mode: 'REPLAY',
      desc_es: 'Publica eventos de anomalía y KPI a la cabina; envía notificaciones por persona.',
      desc_en: 'Publishes anomaly + KPI events to the cockpit; sends per-persona notifications.',
      tools: ['publish_cockpit_event', 'increment_kpi', 'notify_persona'],
    },
    {
      name: 'insights',
      ver: '0.1.0',
      mode: 'REPLAY',
      desc_es: 'Detecta patrones agregados (omisiones, similitudes) y propone seguimientos.',
      desc_en: 'Detects aggregate patterns (omissions, similarities) and proposes follow-ups.',
      tools: ['aggregate_similar_complaints', 'extract_omission_pattern', 'recommend_followup'],
    },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {es ? '5 agentes · 10 herramientas' : '5 agents · 10 tools'}
        </CardTitle>
      </CardHeader>
      <CardBody>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="border-b border-border bg-surface-subtle text-fg-muted">
              <tr>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">Agent</th>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">Ver.</th>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">Modo</th>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">
                  {es ? 'Función' : 'Function'}
                </th>
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">
                  {es ? 'Herramientas' : 'Tools'}
                </th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.name} className="border-b border-border-subtle align-top">
                  <td className="px-2 py-1.5 font-mono font-semibold text-brand-navy">{a.name}</td>
                  <td className="px-2 py-1.5 font-mono text-fg-muted">{a.ver}</td>
                  <td className="px-2 py-1.5">
                    <span
                      className={cn(
                        'rounded-sm px-1.5 py-0.5 font-mono text-2xs uppercase',
                        a.mode === 'LIVE'
                          ? 'bg-brand-cyan text-fg-inverted'
                          : 'bg-surface-subtle text-fg-muted',
                      )}
                    >
                      {a.mode}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-fg">{es ? a.desc_es : a.desc_en}</td>
                  <td className="px-2 py-1.5 font-mono text-xs text-fg-muted">
                    {a.tools.join(', ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardBody>
    </Card>
  );
}

function CodeBlock({ children }: { children: React.ReactNode }) {
  return (
    <pre className="overflow-auto rounded-sbs border border-border-subtle bg-surface-subtle px-3 py-3 font-mono text-xs leading-relaxed">
      {children}
    </pre>
  );
}
