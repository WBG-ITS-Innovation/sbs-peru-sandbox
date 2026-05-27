// Documentation hub — six tabs. Pure client; static content for the
// demo plus the two new technical tabs (agent details with click-in,
// complaint lifecycle, sandbox architecture deep-dive).
//
// i18next literal-string disabled — most strings here are technical
// code snippets, protocol field names, and bilingual labels already
// present in both languages.
/* eslint-disable i18next/no-literal-string */

'use client';

import { useState } from 'react';
import {
  Activity,
  BookOpen,
  Code2,
  Layers,
  Network,
  Repeat,
  Server,
  Sparkles,
} from 'lucide-react';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

type TabKey = 'arch' | 'api' | 'annex' | 'agents' | 'lifecycle' | 'sandbox';

interface Props {
  locale: Locale;
}

export function DocsTabs({ locale }: Props) {
  const es = locale === 'es-PE';
  const [tab, setTab] = useState<TabKey>('arch');

  const tabs: Array<{ key: TabKey; label: string; icon: React.ReactNode }> = [
    { key: 'arch', label: es ? 'Arquitectura' : 'Architecture', icon: <Network className="h-3.5 w-3.5" /> },
    { key: 'sandbox', label: es ? 'Sandbox · técnico' : 'Sandbox · technical', icon: <Server className="h-3.5 w-3.5" /> },
    { key: 'lifecycle', label: es ? 'Ciclo de vida del reclamo' : 'Complaint lifecycle', icon: <Repeat className="h-3.5 w-3.5" /> },
    { key: 'agents', label: es ? 'Agentes y herramientas' : 'Agents & tools', icon: <Sparkles className="h-3.5 w-3.5" /> },
    { key: 'api', label: es ? 'API integradores' : 'Integrator API', icon: <Code2 className="h-3.5 w-3.5" /> },
    { key: 'annex', label: es ? 'Modelo Anexo 1-A' : 'Annex 1-A model', icon: <Layers className="h-3.5 w-3.5" /> },
  ];

  return (
    <div>
      <nav className="flex flex-wrap gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={cn(
              '-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              tab === t.key
                ? 'border-brand-cyan text-brand-navy'
                : 'border-transparent text-fg-muted hover:text-fg',
            )}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </nav>

      <div className="mt-4">
        {tab === 'arch' && <ArchTab es={es} />}
        {tab === 'sandbox' && <SandboxTab es={es} />}
        {tab === 'lifecycle' && <LifecycleTab es={es} />}
        {tab === 'agents' && <AgentsTab es={es} />}
        {tab === 'api' && <ApiTab es={es} />}
        {tab === 'annex' && <AnnexTab es={es} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Architecture tab
// ---------------------------------------------------------------------------

function ArchTab({ es }: { es: boolean }) {
  const steps = es
    ? [
        '1. El cliente reporta un reclamo a su banco / caja / cooperativa.',
        '2. El sistema interno del banco mapea al esquema Anexo 1-A (27 campos).',
        '3. El cliente firma con mTLS, obtiene token OAuth, firma con HMAC.',
        '4. POST /v1/sandbox/complaints/granular con Idempotency-Key.',
        '5. SBS valida la cadena de autenticación y verifica la firma.',
        '6. Tubería de ingesta: PII redactado → DQ → taxonomía → persistencia.',
        '7. Agentes ejecutan: triage → investigación → síntesis → cabina.',
        '8. Supervisor revisa el hallazgo, aprueba, devuelve, o escala a Legal.',
      ]
    : [
        '1. The customer reports a complaint to their bank / caja / cooperative.',
        '2. The institution\'s internal system maps to the Annex 1-A schema (27 fields).',
        '3. The client presents mTLS, obtains OAuth token, computes HMAC.',
        '4. POST /v1/sandbox/complaints/granular with Idempotency-Key.',
        '5. SBS validates the auth chain and verifies the signature.',
        '6. Ingestion pipeline: PII redacted → DQ → taxonomy → persistence.',
        '7. Agents run: triage → investigation → synthesis → cockpit.',
        '8. Supervisor reviews finding, approves, sends back, or escalates to Legal.',
      ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{es ? 'Arquitectura del flujo' : 'Flow architecture'}</CardTitle>
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
   ├─ Triage         (BERT)
   ├─ Investigación  (XGBoost + SHAP + anomalía + draft)
   └─ Síntesis       (LLM · resumen ejecutivo)
       │
       ▼
[Cabina del supervisor]
   ├─ KPIs + insights
   ├─ Procesamiento en vivo
   └─ Approvals (Jefe + Analista)
       │
       ▼
[Aprobación / devolución / escalación]`}
        </pre>
        <ol className="space-y-1.5 text-sm leading-relaxed text-fg">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Sandbox tab — technical deep dive
// ---------------------------------------------------------------------------

function SandboxTab({ es }: { es: boolean }) {
  const sections = es
    ? [
        {
          title: 'mTLS — autenticación de cliente',
          body: 'Cada institución supervisada recibe un certificado X.509 emitido por la CA de desarrollo (dev-ca/). El thumbprint SHA-256 del DER del certificado se almacena en institution_certificates y se valida en cada handshake TLS. En producción la CA será la SBS PKI. Razón de elegir mTLS: identificación criptográfica de la entidad antes de cualquier consumo de recursos.',
        },
        {
          title: 'OAuth 2.0 client_credentials',
          body: 'Tras mTLS, la institución intercambia su client_id + client_secret por un access_token Bearer con scope=complaints:write|read o batch:upload. Scopes y límites por institución viven en oauth_clients. Token vence en 600s. Razón de OAuth además de mTLS: separar identidad (mTLS) de autorización (scopes); revocación rápida de scopes sin re-emisión de certificado.',
        },
        {
          title: 'HMAC SHA-256 — integridad del request',
          body: 'Cada request firma un canonical_request (método + path + host + timestamp + sha256(body) + institution_id) con un secreto HMAC en institution_secrets. La firma viaja en X-SBS-Signature. El timestamp X-SBS-Timestamp tiene ventana de ±300s para protección contra replay. Razón: integridad end-to-end del body aunque un proxy TLS lo termine antes del backend.',
        },
        {
          title: 'Idempotency-Key (RFC draft)',
          body: 'Cada submisión incluye Idempotency-Key (UUID por institución). El backend persiste el par (institution_id, key) → response_payload por 24h en idempotency_records. Reintento con el mismo key devuelve el mismo complaint_id sin doble inserción. Razón: las redes fallan; los retries no deben generar reclamos duplicados.',
        },
        {
          title: 'Postgres + uuid_utils + audit_events',
          body: 'Postgres 15 con extensiones pgvector (embeddings de reclamos) y uuid-ossp. Todo escribir en complaints, agent_runs, audit_events ocurre en transacciones. Cada acción material emite un audit_event con object_id estable y actor identificable. Razón: trazabilidad ante el regulador y reconstrucción forense.',
        },
        {
          title: 'arq + Redis para Tier 2 batch',
          body: 'Tier 2 (uploads CSV vía /v1/batches) encola un job en arq sobre Redis. El worker valida fila por fila con los mismos modelos Pydantic que Tier 1, escribe en complaints, persiste rechazos en batch_row_rejections y dispara un webhook firmado al caller. Razón: aislar el batch latency-tolerante del path NRT crítico.',
        },
        {
          title: 'Webhooks salientes firmados',
          body: 'Los callbacks de Tier 2 (batch completo / fallido) se firman con HMAC en el header X-SBS-Signature. URL de destino se valida contra una allowlist (HTTPS only, FQDN público, no 127.0.0.1 en prod). Reintentos exponenciales 1m/5m/15m/1h/6h, dead-letter después de 5 intentos. Razón: el callback debe sobrevivir caídas de la institución.',
        },
        {
          title: 'Roles y CSRF (ADR 0040)',
          body: 'Supervisora (María), Analista (Lucía), Jefe (Jorge) son personas con roles distintos. Approvals y Send-to-approvals requieren analyst|head. El UI usa double-submit CSRF (cookie sbs-csrf + header x-sbs-csrf) en todas las acciones de estado. Razón: separación de funciones y defensa en profundidad.',
        },
      ]
    : [
        {
          title: 'mTLS — client authentication',
          body: 'Each supervised institution gets an X.509 cert issued by the dev CA (dev-ca/). The SHA-256 thumbprint of the cert\'s DER is stored in institution_certificates and validated at every TLS handshake. In production the CA is the SBS PKI. Why mTLS: cryptographic entity identification before any resource consumption.',
        },
        {
          title: 'OAuth 2.0 client_credentials',
          body: 'After mTLS, the institution swaps client_id + client_secret for a Bearer access_token with scope=complaints:write|read or batch:upload. Scopes and per-institution limits live in oauth_clients. Token expires in 600s. Why OAuth on top of mTLS: separates identity (mTLS) from authorization (scopes); fast revocation without cert re-issuance.',
        },
        {
          title: 'HMAC SHA-256 — request integrity',
          body: 'Each request signs a canonical_request (method + path + host + timestamp + sha256(body) + institution_id) with an HMAC secret in institution_secrets. The signature rides X-SBS-Signature. The X-SBS-Timestamp has a ±300s replay window. Why: end-to-end body integrity even if a TLS proxy terminates before backend.',
        },
        {
          title: 'Idempotency-Key (RFC draft)',
          body: 'Every submission carries Idempotency-Key (UUID per institution). The backend persists (institution_id, key) → response_payload for 24h in idempotency_records. Retry with the same key returns the same complaint_id without double-insert. Why: networks fail; retries must not duplicate complaints.',
        },
        {
          title: 'Postgres + uuid_utils + audit_events',
          body: 'Postgres 15 with pgvector (complaint embeddings) and uuid-ossp. All writes to complaints, agent_runs, audit_events happen in transactions. Every material action emits an audit_event with a stable object_id and identifiable actor. Why: regulator traceability and forensic reconstruction.',
        },
        {
          title: 'arq + Redis for Tier 2 batch',
          body: 'Tier 2 (CSV uploads via /v1/batches) enqueues an arq job on Redis. The worker validates row-by-row using the same Pydantic models as Tier 1, writes to complaints, persists rejections in batch_row_rejections, and fires a signed webhook to the caller. Why: isolate latency-tolerant batch from the critical NRT path.',
        },
        {
          title: 'Signed outbound webhooks',
          body: 'Tier 2 callbacks (batch complete / failed) are HMAC-signed in the X-SBS-Signature header. Destination URL is allowlist-validated (HTTPS only, public FQDN, no 127.0.0.1 in prod). Exponential retry 1m/5m/15m/1h/6h, dead-letter after 5 attempts. Why: the callback must survive institution outages.',
        },
        {
          title: 'Roles + CSRF (ADR 0040)',
          body: 'Supervisor (María), Analyst (Lucía), Head (Jorge) are personas with distinct roles. Approvals and Send-to-approvals require analyst|head. The UI uses double-submit CSRF (sbs-csrf cookie + x-sbs-csrf header) on every state-changing action. Why: separation of duties and defense in depth.',
        },
      ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {es ? 'Sandbox · arquitectura técnica' : 'Sandbox · technical architecture'}
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        {sections.map((s, i) => (
          <div key={i} className="rounded-sbs border border-border-subtle bg-surface-subtle p-3">
            <p className="text-sm font-semibold text-brand-navy">{s.title}</p>
            <p className="mt-1 text-xs leading-relaxed text-fg">{s.body}</p>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Lifecycle tab
// ---------------------------------------------------------------------------

function LifecycleTab({ es }: { es: boolean }) {
  const phases = es
    ? [
        {
          name: '1. Recepción',
          who: 'Cliente → Institución',
          what: 'El cliente entrega su queja por canal web, telefónico, oficina o aplicativo móvil. La institución abre un caso interno (con su propio COD_REC) y un plazo de respuesta (30 días por defecto).',
          artifact: 'Caso interno con narrativa cruda y PII',
        },
        {
          name: '2. Triage interno',
          who: 'Institución',
          what: 'El operador del banco mapea los campos del caso interno al esquema Anexo 1-A (27 campos). Aún no se ha enviado nada a SBS.',
          artifact: 'Registro Anexo 1-A en el sistema interno',
        },
        {
          name: '3. Envío a SBS',
          who: 'Institución → SBS API',
          what: 'POST /v1/sandbox/complaints/granular firmado (mTLS + OAuth + HMAC + Idempotency-Key). La SBS responde 201 con un complaint_id canónico de SBS.',
          artifact: 'complaint_id canónico + receipt',
        },
        {
          name: '4. Pipeline de ingesta',
          who: 'SBS · ingestion-orchestrator',
          what: 'El reclamo pasa por 5 etapas determinísticas: validación de la firma → redacción de PII → calidad de datos → normalización taxonómica → persistencia canónica.',
          artifact: 'Registro en complaints (PII-free) + audit chain',
        },
        {
          name: '5. Procesamiento agéntico',
          who: 'SBS · triage / investigation / synthesis',
          what: 'Tres agentes procesan en secuencia: triage clasifica (BERT), investigación atribuye features (XGBoost+SHAP), calcula anomalía, busca similares y compone borrador, síntesis produce el resumen ejecutivo.',
          artifact: 'agent_runs con tool_calls + final_output',
        },
        {
          name: '6. Cabina del supervisor',
          who: 'SBS · María (Supervisora)',
          what: 'El reclamo aparece en la cabina con su anomalía. María revisa el borrador, los SHAP, los reclamos similares. Puede aprobar, observar, pedir revisión humana, devolver a la entidad, o enviar a aprobaciones (Lucía / Jorge).',
          artifact: 'Decisión humana auditada',
        },
        {
          name: '7. Aprobaciones',
          who: 'SBS · Lucía (Analista) o Jorge (Jefe)',
          what: 'Hallazgos enviados a la cola de aprobaciones reciben una segunda mirada. Lucía puede aprobar, ajustar el borrador, o pedir más información a la entidad. Jorge tiene la última palabra antes del envío externo.',
          artifact: 'pending_approvals con resolución firme',
        },
        {
          name: '8. Cierre / escalación',
          who: 'SBS → Institución (o Legal)',
          what: 'Si se aprueba, se cierra y se notifica a la entidad (resolución a favor del usuario, a favor de la entidad, o anulado). Si se escala, abre expediente con el Departamento Legal.',
          artifact: 'Resolución + notificación firmada',
        },
      ]
    : [
        {
          name: '1. Intake',
          who: 'Customer → Institution',
          what: 'Customer submits the complaint via web, phone, branch, or mobile app. The institution opens an internal case (with its own COD_REC) and a response deadline (30 days default).',
          artifact: 'Internal case with raw narrative + PII',
        },
        {
          name: '2. Internal triage',
          who: 'Institution',
          what: 'The bank\'s back office maps the internal case fields to the Annex 1-A schema (27 fields). Nothing has been sent to SBS yet.',
          artifact: 'Annex 1-A record in the internal system',
        },
        {
          name: '3. Submission to SBS',
          who: 'Institution → SBS API',
          what: 'Signed POST /v1/sandbox/complaints/granular (mTLS + OAuth + HMAC + Idempotency-Key). SBS responds 201 with a canonical complaint_id.',
          artifact: 'Canonical complaint_id + receipt',
        },
        {
          name: '4. Ingestion pipeline',
          who: 'SBS · ingestion-orchestrator',
          what: 'The complaint passes through 5 deterministic stages: signature verification → PII redaction → data quality → taxonomy normalization → canonical persistence.',
          artifact: 'Row in complaints (PII-free) + audit chain',
        },
        {
          name: '5. Agent processing',
          who: 'SBS · triage / investigation / synthesis',
          what: 'Three agents run in sequence: triage classifies (BERT), investigation attributes features (XGBoost+SHAP), computes anomaly, finds similar complaints, drafts a narrative; synthesis produces the executive summary.',
          artifact: 'agent_runs with tool_calls + final_output',
        },
        {
          name: '6. Supervisor cockpit',
          who: 'SBS · María (Supervisor)',
          what: 'The complaint appears in the cockpit with its anomaly. María reviews the draft, SHAP, similar complaints. She can approve, observe, request manual review, send back to the entity, or send to approvals (Lucía / Jorge).',
          artifact: 'Audited human decision',
        },
        {
          name: '7. Approvals',
          who: 'SBS · Lucía (Analyst) or Jorge (Head)',
          what: 'Findings sent to the approvals queue get a second pair of eyes. Lucía can approve, edit the draft, or request more from the entity. Jorge has final sign-off before external notification.',
          artifact: 'pending_approvals with binding resolution',
        },
        {
          name: '8. Closure / escalation',
          who: 'SBS → Institution (or Legal)',
          what: 'If approved, the complaint closes and the entity is notified (resolution favouring user, entity, or annulled). If escalated, a file opens with the Legal Department.',
          artifact: 'Resolution + signed notification',
        },
      ];
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          {es ? 'Ciclo de vida de un reclamo' : 'Complaint lifecycle'}
        </CardTitle>
      </CardHeader>
      <CardBody>
        <ol className="relative space-y-3 border-l-2 border-brand-cyan/30 pl-6">
          {phases.map((p, i) => (
            <li key={i} className="relative">
              <span
                aria-hidden
                className="absolute -left-8 top-1 flex h-5 w-5 items-center justify-center rounded-full border-2 border-brand-cyan bg-surface text-2xs font-bold text-brand-navy"
              >
                {i + 1}
              </span>
              <p className="text-sm font-semibold text-brand-navy">{p.name}</p>
              <p className="text-2xs font-mono text-fg-muted">{p.who}</p>
              <p className="mt-1 text-xs leading-relaxed text-fg">{p.what}</p>
              <p className="mt-1 text-2xs font-mono text-fg-muted">
                {es ? 'Artefacto' : 'Artifact'}: {p.artifact}
              </p>
            </li>
          ))}
        </ol>
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Agents tab — clickable per-agent detail
// ---------------------------------------------------------------------------

interface AgentDoc {
  name: string;
  ver: string;
  mode: 'LIVE' | 'REPLAY';
  blurb_es: string;
  blurb_en: string;
  tools: Array<{ name: string; desc_es: string; desc_en: string }>;
  input_example: string;
  output_example: string;
}

const AGENT_DOCS: AgentDoc[] = [
  {
    name: 'triage',
    ver: '0.1.0',
    mode: 'LIVE',
    blurb_es: 'Clasifica el reclamo en una de 8-12 categorías de conducta de mercado. Sale rápido y con explicación clara: etiqueta + confianza + 3 alternativas. Si la confianza es baja (< 0.65), marca confidence_degraded=true para que el supervisor sepa que el modelo no estaba seguro.',
    blurb_en: 'Classifies the complaint into one of 8-12 market-conduct categories. Fast with clear explanation: label + confidence + 3 alternatives. Low confidence (<0.65) flags confidence_degraded=true so the supervisor knows the model was unsure.',
    tools: [
      {
        name: 'bert_classifier',
        desc_es: 'BERT en español fine-tuned sobre 12k reclamos históricos SBS. Devuelve label + confidence. Versión actual: bert-classifier-0.1.0.',
        desc_en: 'Spanish BERT fine-tuned on 12k historical SBS complaints. Returns label + confidence. Current version: bert-classifier-0.1.0.',
      },
    ],
    input_example: `{
  "complaint_id": "BCO-2026-1234567",
  "narrative": "Cliente reporta cargo no reconocido...",
  "product_category": "TARJETA_CREDITO",
  "channel": "APP_MOVIL"
}`,
    output_example: `{
  "classification": {
    "label": "undisclosed-fees-credit",
    "confidence": 0.87,
    "model_id": "bert-classifier-0.1.0",
    "alternatives": [
      {"label": "operations-not-recognized", "confidence": 0.06},
      {"label": "service-quality", "confidence": 0.04}
    ]
  },
  "severity_recommendation": "HIGH"
}`,
  },
  {
    name: 'investigation',
    ver: '0.1.0',
    mode: 'LIVE',
    blurb_es: 'El agente más complejo. Atribuye qué features empujan la clasificación (XGBoost + SHAP), calcula un composite_score de anomalía con 6 contribuyentes, busca reclamos similares por embedding y compone un borrador inicial para el supervisor.',
    blurb_en: 'The most complex agent. Attributes which features drive the classification (XGBoost+SHAP), computes a composite anomaly score with 6 contributors, finds similar complaints by embedding, and composes an initial draft for the supervisor.',
    tools: [
      {
        name: 'rank_features',
        desc_es: 'XGBoost ranker que ordena las top-N features por contribución SHAP. Devuelve nombre, contribución signada, y model_id.',
        desc_en: 'XGBoost ranker that orders the top-N features by SHAP contribution. Returns name, signed contribution, and model_id.',
      },
      {
        name: 'anomaly_detector',
        desc_es: 'Compone un score 0-1 con 6 contribuyentes: gap de divulgación, tasa-vs-pares, patrón textual, severidad, antigüedad, edad del cliente. Umbral 0.70 publica anomalía.',
        desc_en: 'Composes a 0-1 score with 6 contributors: disclosure gap, rate-vs-peers, textual pattern, severity, recency, customer age. Threshold 0.70 publishes anomaly.',
      },
      {
        name: 'search_similar_complaints',
        desc_es: 'Busca por similitud de embedding (pgvector) en los últimos 90 días. Devuelve top-10 con similarity score.',
        desc_en: 'Searches by embedding similarity (pgvector) over the last 90 days. Returns top-10 with similarity score.',
      },
      {
        name: 'draft_narrative',
        desc_es: 'Compone un borrador objetivo (2-4 párrafos) para el supervisor con LLM gpt-4o-mini. Cita los SHAP top y los reclamos similares.',
        desc_en: 'Composes an objective draft (2-4 paragraphs) for the supervisor with gpt-4o-mini LLM. Cites top SHAP features and similar complaints.',
      },
    ],
    input_example: `{
  "complaint_id": "BCO-2026-1234567",
  "classification_label": "undisclosed-fees-credit",
  "classification_confidence": 0.87
}`,
    output_example: `{
  "feature_attribution": [
    {"name": "narrative_mentions_fee_undisclosed", "contribution": 0.27},
    {"name": "product_is_credit_or_card", "contribution": 0.18}
  ],
  "anomaly": {
    "composite_score": 0.74,
    "threshold": 0.70,
    "contributors": [
      {"signal": "fee_disclosure_gap", "weight": 0.42}
    ]
  },
  "similar_complaints": [
    {"complaint_id": "BCO-2026-4427703", "similarity": 0.91}
  ],
  "draft_narrative": {"text": "El reclamo describe..."}
}`,
  },
  {
    name: 'synthesis',
    ver: '0.1.0',
    mode: 'LIVE',
    blurb_es: 'Toma todo lo producido (clasificación + features + anomalía + draft) y produce un resumen ejecutivo de 3-5 viñetas para la supervisora. Usa LLM con prompt anclado en los SHAP. La salida es texto plano y cita códigos taxonómicos.',
    blurb_en: 'Takes everything produced (classification + features + anomaly + draft) and produces a 3-5 bullet executive summary for the supervisor. Uses LLM with prompt grounded in SHAP. Output is plain text and cites taxonomy codes.',
    tools: [
      {
        name: 'compose_executive_summary',
        desc_es: 'LLM gpt-4o-mini con contexto de 1500 tokens. Genera text + key_points + audience.',
        desc_en: 'gpt-4o-mini LLM with 1500-token context. Generates text + key_points + audience.',
      },
    ],
    input_example: `{
  "complaint_id": "BCO-2026-1234567",
  "classification": {...},
  "anomaly": {...},
  "draft_narrative": {...}
}`,
    output_example: `{
  "executive_summary": {
    "text": "Anomalía compuesta 0.74 (umbral 0.70). El borrador del agente narra...",
    "key_points": [
      "Anomalía 0.74 > umbral 0.70",
      "Borrador omite término clave: comisión por mantenimiento",
      "Coincide con 3 reclamos similares (>0.84 similitud)"
    ],
    "audience": "supervisor",
    "model_id": "synthesis-0.1.0"
  }
}`,
  },
  {
    name: 'cockpit-monitor',
    ver: '0.1.0',
    mode: 'REPLAY',
    blurb_es: 'Publica eventos de anomalía y métricas a la cabina de la supervisora. Incrementa KPIs (complaints_24h, anomalies_active) y dispara notificaciones por persona.',
    blurb_en: 'Publishes anomaly events and metrics to the supervisor cockpit. Increments KPIs (complaints_24h, anomalies_active) and triggers per-persona notifications.',
    tools: [
      { name: 'publish_cockpit_event', desc_es: 'Empuja un evento a SSE cockpit topic.', desc_en: 'Pushes an event to the cockpit SSE topic.' },
      { name: 'increment_kpi', desc_es: 'Atomic increment de un KPI con TTL diario.', desc_en: 'Atomic KPI increment with daily TTL.' },
      { name: 'notify_persona', desc_es: 'Push notification por persona y prioridad.', desc_en: 'Push notification per persona and priority.' },
    ],
    input_example: `{"complaint_id": "...", "anomaly_score": 0.74}`,
    output_example: `{"published": true, "kpis_updated": ["complaints_24h", "anomalies_active"]}`,
  },
  {
    name: 'insights',
    ver: '0.1.0',
    mode: 'REPLAY',
    blurb_es: 'Agente de patrones agregados. Detecta clusters de omisiones similares, recomienda follow-ups y propone investigaciones temáticas al cumplimiento (Sergio).',
    blurb_en: 'Aggregate-pattern agent. Detects clusters of similar omissions, recommends follow-ups, and proposes thematic investigations to compliance (Sergio).',
    tools: [
      { name: 'aggregate_similar_complaints', desc_es: 'Agrupa en ventana de 30 días por similitud > 0.85.', desc_en: 'Groups in a 30-day window by similarity > 0.85.' },
      { name: 'extract_omission_pattern', desc_es: 'Detecta términos críticos ausentes en los borradores.', desc_en: 'Detects critical terms missing from drafts.' },
      { name: 'recommend_followup', desc_es: 'Sugiere una acción de seguimiento al persona.', desc_en: 'Suggests a follow-up action to the persona.' },
    ],
    input_example: `{"window": "30d", "min_similarity": 0.85}`,
    output_example: `{"clusters_detected": 1, "recommended_followup": "review BANCO_DEMO_001 contract clauses"}`,
  },
];

function AgentsTab({ es }: { es: boolean }) {
  const [selected, setSelected] = useState<string>(AGENT_DOCS[0].name);
  const agent = AGENT_DOCS.find((a) => a.name === selected) || AGENT_DOCS[0];
  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{es ? '5 agentes' : '5 agents'}</CardTitle>
        </CardHeader>
        <CardBody className="space-y-1">
          {AGENT_DOCS.map((a) => (
            <button
              key={a.name}
              type="button"
              onClick={() => setSelected(a.name)}
              className={cn(
                'flex w-full items-center justify-between rounded-sbs border px-2 py-1.5 text-left text-sm transition-colors',
                selected === a.name
                  ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy'
                  : 'border-border-subtle bg-surface text-fg hover:bg-surface-subtle',
              )}
            >
              <span className="font-mono">{a.name}</span>
              <span
                className={cn(
                  'rounded-sm px-1.5 py-0.5 font-mono text-2xs',
                  a.mode === 'LIVE' ? 'bg-brand-cyan text-fg-inverted' : 'bg-fg-muted/20 text-fg',
                )}
              >
                {a.mode}
              </span>
            </button>
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              <span className="font-mono">{agent.name}</span>
              <span className="font-mono text-xs text-fg-muted">v{agent.ver}</span>
            </span>
            <span
              className={cn(
                'rounded-sm px-2 py-0.5 font-mono text-2xs',
                agent.mode === 'LIVE' ? 'bg-brand-cyan text-fg-inverted' : 'bg-fg-muted/20 text-fg',
              )}
            >
              {agent.mode}
            </span>
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-sm leading-relaxed text-fg">{es ? agent.blurb_es : agent.blurb_en}</p>

          <div>
            <p className="mb-1.5 flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-fg-muted">
              <BookOpen className="h-3 w-3" />
              {es ? 'Herramientas' : 'Tools'}
            </p>
            <ul className="space-y-1">
              {agent.tools.map((t) => (
                <li key={t.name} className="rounded-sbs border border-border-subtle bg-surface-subtle p-2">
                  <p className="font-mono text-xs font-semibold text-brand-navy">{t.name}</p>
                  <p className="mt-0.5 text-2xs text-fg">{es ? t.desc_es : t.desc_en}</p>
                </li>
              ))}
            </ul>
          </div>

          <div className="grid gap-2 lg:grid-cols-2">
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-muted">
                {es ? 'Ejemplo de entrada' : 'Input example'}
              </p>
              <CodeBlock>{agent.input_example}</CodeBlock>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-muted">
                {es ? 'Ejemplo de salida' : 'Output example'}
              </p>
              <CodeBlock>{agent.output_example}</CodeBlock>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// API + Annex tabs (kept compact)
// ---------------------------------------------------------------------------

function ApiTab({ es: _es }: { es: boolean }) {
  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">cURL · POST /v1/sandbox/complaints/granular</CardTitle>
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
          <CardTitle className="text-base">OAuth 2.0 client_credentials</CardTitle>
        </CardHeader>
        <CardBody>
          <CodeBlock>
{`curl -sS -X POST https://sbs.gob.pe/v1/oauth/token \\
  --cert dev-ca/banco-demo-001.pem \\
  --key  dev-ca/banco-demo-001-key.pem \\
  -u "banco-demo-001:$CLIENT_SECRET" \\
  -d "grant_type=client_credentials&scope=complaints:write complaints:read"`}
          </CodeBlock>
        </CardBody>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">HMAC SHA-256 canonical request</CardTitle>
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
    { key: 'EST_REC', type: 'enum', desc_es: 'Estado del reclamo (pendiente/atendido/anulado)', desc_en: 'Status', req: true },
    { key: 'COD_PRV', type: 'string', desc_es: 'Código del reclamo previo', desc_en: 'Previous complaint code', req: false },
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
                <th className="px-2 py-1.5 text-left font-mono uppercase tracking-wide">{es ? 'Descripción' : 'Description'}</th>
                <th className="px-2 py-1.5 text-center font-mono uppercase tracking-wide">{es ? 'Obligatorio' : 'Required'}</th>
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

function CodeBlock({ children }: { children: React.ReactNode }) {
  return (
    <pre className="overflow-auto rounded-sbs border border-border-subtle bg-surface-subtle px-3 py-3 font-mono text-xs leading-relaxed">
      {children}
    </pre>
  );
}
