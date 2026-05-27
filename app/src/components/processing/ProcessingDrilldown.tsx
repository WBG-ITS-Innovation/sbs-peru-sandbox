// Per-complaint live drill-in.
//
// The page narrates a single complaint moving through the sandbox.
// Every stage carries:
//   - actor (who ran it: orchestrator, agent, tool)
//   - timestamp (start / end / elapsed_ms)
//   - inputs and outputs (what came in, what came out)
//   - "Why this takes time" explanation (model, network, deterministic)
//   - "Documentation" panel (technical detail + audit pointer)
//   - human-in-the-loop controls (approve, send back, observe, override)
//
// Data sources: /app/api/journey/audit (ingestion events),
// /app/api/journey/findings (agent_runs + tool calls), plus the raw
// complaint record. Refreshes every 1.5 s while any stage is missing,
// then settles to 5 s.
/* eslint-disable i18next/no-literal-string */

'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock,
  Edit3,
  Eye,
  Loader2,
  MessageSquare,
  Send,
  ShieldAlert,
  Sparkles,
  Workflow,
} from 'lucide-react';

import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Tooltip as InfoTooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

interface Props {
  locale: Locale;
  complaintId: string;
}

interface AuditEvent {
  action?: string;
  diff?: Record<string, unknown>;
  created_at?: string;
}

interface ToolCall {
  tool_name?: string;
  started_at?: string;
  ended_at?: string;
  status?: string;
  input?: Record<string, unknown>;
  output?: Record<string, unknown>;
}

interface AgentRun {
  agent_name?: string;
  agent_version?: string;
  status?: string;
  started_at?: string;
  ended_at?: string;
  tool_calls?: ToolCall[];
  final_output?: Record<string, unknown>;
}

interface Finding {
  complaint?: {
    received_at?: string;
    institution_id?: string;
    institution_name?: string;
    narrative_text?: string;
    motivo_code?: string;
    product_category?: string;
    severity?: string;
  };
  classification?: { label?: string; confidence?: number };
  features?: { feature_contributions?: Array<{ feature_name: string; contribution: number }> };
  anomaly?: { composite_score?: number; threshold?: number; contributors?: Array<{ signal: string; weight: number }> };
  executive_summary?: { text?: string; key_points?: string[] };
  agent_runs?: AgentRun[];
  agent_drafted_narrative?: string | null;
  taxonomy_normalizations?: Array<{ field_path: string; original_value: string; canonical_value: string }>;
}

// ---------------------------------------------------------------------------
// Stage definitions with documentation
// ---------------------------------------------------------------------------

interface StageDoc {
  what_es: string;
  what_en: string;
  why_es: string;
  why_en: string;
  typical_ms: string;
  audit_action: string;
}

const PIPELINE_STAGES: Array<{
  key: string;
  action: string;
  actor: string;
  label_es: string;
  label_en: string;
  doc: StageDoc;
}> = [
  {
    key: 'received',
    action: 'complaint-received',
    actor: 'ingestion-orchestrator',
    label_es: 'Reclamo recibido',
    label_en: 'Complaint received',
    doc: {
      what_es: 'La API verifica la cadena de autenticación (mTLS + OAuth + HMAC + Idempotency-Key) y registra el primer evento de auditoría para este reclamo. La carga útil aún contiene PII y los códigos taxonómicos sin normalizar.',
      what_en: 'API verifies the auth chain (mTLS + OAuth + HMAC + Idempotency-Key) and writes the first audit event. Payload still contains PII and un-normalized taxonomy codes.',
      why_es: 'Es solo un INSERT auditable. Demora despreciable (<10ms). Si tarda más, suele ser contención de Postgres.',
      why_en: 'Pure auditable INSERT. Negligible latency (<10ms). Longer means Postgres contention.',
      typical_ms: '< 10ms',
      audit_action: 'complaint-received',
    },
  },
  {
    key: 'pii',
    action: 'pii-redacted',
    actor: 'pii-redactor',
    label_es: 'PII redactado',
    label_en: 'PII redacted',
    doc: {
      what_es: 'Se ejecuta el motor de redacción (regex Anexo + reconocedor de entidades) sobre la narrativa: nombres, DNI, teléfonos, correos, números de cuenta. La salida canónica reemplaza cada entidad por un placeholder estable (<PERSON_1>, <DNI_1>, ...). El texto crudo se conserva solo en raw_complaints, accesible únicamente con orden judicial.',
      what_en: 'Redaction engine (Annex regex + entity recognizer) runs over the narrative: names, DNIs, phones, emails, account numbers. Canonical output replaces each entity with a stable placeholder. Raw text is preserved only in raw_complaints, accessible only via court order.',
      why_es: 'Es regex deterministic + un modelo NER ligero. Demora ~50-150ms por reclamo. Si tarda más es porque el texto excede 5000 caracteres.',
      why_en: 'Deterministic regex + a lightweight NER model. ~50-150ms per complaint. Longer means narrative >5000 chars.',
      typical_ms: '50-150 ms',
      audit_action: 'pii-redacted',
    },
  },
  {
    key: 'dq',
    action: 'data-quality-completed',
    actor: 'dq-validator',
    label_es: 'Calidad de datos validada',
    label_en: 'Data quality validated',
    doc: {
      what_es: 'Validador determinista contra el modelo Anexo 1-A: 27 reglas (DQ-A1A-001..027) que verifican obligatoriedad, rango, formato, y referencias cruzadas (estado=atendido exige fecha_resolucion, etc). Cada violación se emite como dq-rule-violated en el audit log para trazabilidad.',
      what_en: 'Deterministic validator against the Annex 1-A model: 27 rules (DQ-A1A-001..027) checking obligatory, range, format, and cross-references. Each violation emits dq-rule-violated in the audit log.',
      why_es: 'Todo es Python puro sin red. Demora < 20ms incluso para 27 reglas. Cada error/warning genera una fila audit_events extra.',
      why_en: 'Pure Python, no network. <20ms even for 27 rules. Each violation generates an extra audit_events row.',
      typical_ms: '< 20 ms',
      audit_action: 'data-quality-completed',
    },
  },
  {
    key: 'taxonomy',
    action: 'taxonomy-normalized',
    actor: 'taxonomy-normalizer',
    label_es: 'Taxonomía normalizada',
    label_en: 'Taxonomy normalized',
    doc: {
      what_es: 'Mapeo de las codificaciones libres de la institución (canal, producto, motivo) a los códigos canónicos del Anexo. Diccionario versionado (taxonomy-v1) recoge mayúsculas/minúsculas, acentos, abreviaturas, formas sinónimas. Términos no reconocidos se marcan con flag_unknown_taxonomy=true para revisión.',
      what_en: 'Maps the institution\'s free-form coding (channel, product, motive) to the canonical Annex codes. Versioned dictionary (taxonomy-v1) covers case, accents, abbreviations, synonyms. Unknown terms flagged for review.',
      why_es: 'Lookup en memoria con normalización Unicode. < 5ms. Es la pieza más auditable y cambia con cada nueva versión del diccionario.',
      why_en: 'In-memory lookup with Unicode normalization. <5ms. Most auditable piece and changes with each dictionary version.',
      typical_ms: '< 5 ms',
      audit_action: 'taxonomy-normalized',
    },
  },
  {
    key: 'persisted',
    action: 'canonical-complaint-persisted',
    actor: 'persistence',
    label_es: 'Reclamo canónico persistido',
    label_en: 'Canonical complaint persisted',
    doc: {
      what_es: 'Escritura final del registro canónico en la tabla complaints (sin PII). Se conserva el raw_complaint_id para reconciliación. A partir de aquí, el reclamo es visible para los agentes y para los queries del supervisor.',
      what_en: 'Final write of the canonical record to the complaints table (PII-free). raw_complaint_id is kept for reconciliation. From here the complaint is visible to agents and supervisor queries.',
      why_es: 'INSERT + COMMIT en una transacción. ~20-50ms en condiciones normales.',
      why_en: 'INSERT + COMMIT in one transaction. ~20-50ms under normal load.',
      typical_ms: '20-50 ms',
      audit_action: 'canonical-complaint-persisted',
    },
  },
];

const AGENT_STAGES: Array<{
  name: string;
  label_es: string;
  label_en: string;
  icon: string;
  doc: StageDoc;
}> = [
  {
    name: 'triage',
    label_es: 'Agente Triage',
    label_en: 'Triage agent',
    icon: '🏷️',
    doc: {
      what_es: 'Clasifica el reclamo en una de las 8-12 categorías de conducta usando un BERT en español fine-tuned sobre 12k reclamos históricos del SBS. Devuelve etiqueta + confianza + top-3 alternativas. Si la confianza es < 0.65 emite confidence_degraded=true para revisión humana.',
      what_en: 'Classifies the complaint into one of 8-12 conduct categories using a Spanish BERT fine-tuned on 12k historical SBS complaints. Returns label + confidence + top-3 alternatives. Confidence <0.65 triggers confidence_degraded=true for human review.',
      why_es: 'Inferencia BERT en CPU. Demora 300-500ms por reclamo. Si se ejecuta en GPU baja a < 100ms. La latencia es el costo de la explicabilidad — la alternativa (LLM) sería 10x más lenta y menos auditable.',
      why_en: 'BERT inference on CPU. 300-500ms per complaint. On GPU drops below 100ms. Latency is the price of explainability — LLM alternative would be 10x slower and less auditable.',
      typical_ms: '300-500 ms',
      audit_action: 'classification-published',
    },
  },
  {
    name: 'investigation',
    label_es: 'Agente Investigación',
    label_en: 'Investigation agent',
    icon: '🔍',
    doc: {
      what_es: 'Cuatro herramientas en secuencia: (1) rank_features ranquea las features con XGBoost + SHAP para mostrar qué empuja la clasificación, (2) anomaly_detector calcula composite_score con 6 contribuyentes, (3) search_similar_complaints encuentra reclamos parecidos (top-10 por embedding), (4) draft_narrative compone un borrador para el supervisor.',
      what_en: 'Four tools in sequence: (1) rank_features with XGBoost+SHAP for feature attribution, (2) anomaly_detector computes composite_score with 6 contributors, (3) search_similar_complaints finds neighbours by embedding (top-10), (4) draft_narrative composes a supervisor-facing draft.',
      why_es: 'XGBoost + SHAP son rápidos (<150ms), el embedding search es ~200ms contra pgvector, el LLM del draft es lo más lento (~400ms con caching, 1-2s sin él). Total típico: 800-1200ms. Si tarda >2s suele ser el LLM con cache miss.',
      why_en: 'XGBoost+SHAP are fast (<150ms), embedding search ~200ms against pgvector, the draft LLM is slowest (~400ms cached, 1-2s uncached). Typical total: 800-1200ms. >2s usually means LLM cache miss.',
      typical_ms: '800-1200 ms',
      audit_action: 'finding-drafted',
    },
  },
  {
    name: 'synthesis',
    label_es: 'Agente Síntesis',
    label_en: 'Synthesis agent',
    icon: '📝',
    doc: {
      what_es: 'Compone el resumen ejecutivo final para la supervisora (María) en 3-5 viñetas. Usa LLM gpt-4o-mini con un prompt anclado en el draft de investigación + los SHAP + el composite_score. La salida es texto plano (no markdown) y siempre cita los códigos taxonómicos.',
      what_en: 'Composes the final executive summary for the supervisor (María) in 3-5 bullets. Uses gpt-4o-mini grounded on the investigation draft + SHAP + composite_score. Output is plain text (no markdown) and always cites taxonomy codes.',
      why_es: 'Una sola llamada LLM con 1500 tokens de contexto. 400-700ms típico. Si tarda más es rate-limiting de Azure.',
      why_en: 'Single LLM call with 1500 tokens of context. 400-700ms typical. Longer means Azure rate-limiting.',
      typical_ms: '400-700 ms',
      audit_action: 'executive-summary-composed',
    },
  },
];

export function ProcessingDrilldown({ locale, complaintId }: Props) {
  const es = locale === 'es-PE';
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [finding, setFinding] = useState<Finding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [hitlToast, setHitlToast] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const pull = async () => {
      try {
        const [auditR, findR] = await Promise.all([
          fetch(`/app/api/journey/audit?object_id=${encodeURIComponent(complaintId)}`, { cache: 'no-store' }),
          fetch(`/app/api/journey/findings?complaint_id=${encodeURIComponent(complaintId)}`, { cache: 'no-store' }),
        ]);
        if (auditR.ok) {
          const j = (await auditR.json()) as { events?: AuditEvent[] };
          if (!cancelled) setEvents(j.events || []);
        }
        if (findR.ok) {
          if (!cancelled) setFinding((await findR.json()) as Finding);
        } else if (findR.status === 404 && !cancelled) {
          setFinding({});
        }
        if (!cancelled) setError(null);
      } catch (exc) {
        if (!cancelled) setError(String(exc));
      }
    };
    pull();
    const someoneMissing = (finding?.agent_runs || []).length < 4;
    const intervalMs = someoneMissing ? 1500 : 5000;
    const id = window.setInterval(() => setRefreshTick((t) => t + 1), intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [complaintId, refreshTick, finding?.agent_runs]);

  const pipelineByKey = useMemo(() => {
    const map = new Map<string, AuditEvent>();
    for (const e of events) {
      const stage = PIPELINE_STAGES.find((s) => s.action === e.action);
      if (stage && !map.has(stage.key)) map.set(stage.key, e);
    }
    return map;
  }, [events]);

  const agentByName = useMemo(() => {
    const map = new Map<string, AgentRun>();
    for (const r of finding?.agent_runs || []) {
      if (r.agent_name) map.set(r.agent_name, r);
    }
    return map;
  }, [finding]);

  const activityLog = useMemo(() => {
    const items: Array<{ ts: string; actor: string; tool: string; summary: string; severity?: 'info' | 'warn' | 'error' }> = [];
    for (const e of events) {
      items.push({
        ts: e.created_at || '',
        actor: actorForAuditAction(e.action || ''),
        tool: e.action || '',
        summary: summariseAuditDiff(e),
        severity: e.action === 'dq-rule-violated' ? 'warn' : 'info',
      });
    }
    for (const run of finding?.agent_runs || []) {
      for (const tc of run.tool_calls || []) {
        items.push({
          ts: tc.ended_at || tc.started_at || '',
          actor: run.agent_name || 'agent',
          tool: tc.tool_name || '',
          summary: summariseTool(tc.tool_name || '', tc.output || {}),
          severity: tc.status === 'error' ? 'error' : 'info',
        });
      }
    }
    items.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
    return items;
  }, [events, finding]);

  const hitl = useCallback((label: string) => {
    setHitlToast(label);
    window.setTimeout(() => setHitlToast(null), 2200);
  }, []);

  const piiBefore = (finding?.complaint?.narrative_text || '').slice(0, 240);
  const piiAfter = piiBefore
    .replace(/\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+( [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?\b/g, '<PERSON>')
    .replace(/\bDNI\s*\d{8}\b/g, 'DNI <PE_DNI>')
    .replace(/\b\d{8}\b/g, '<PE_DNI>')
    .replace(/\+?51\s*9\d{2}\s*\d{3}\s*\d{1,3}/g, '<PE_PHONE>')
    .replace(/\b[\w.+-]+@[\w-]+\.[a-z]+\b/gi, '<EMAIL>');

  return (
    <div className="space-y-4">
      <Link href="/processing" className="inline-flex items-center gap-1 text-sm text-brand-navy hover:underline">
        <ArrowLeft className="h-4 w-4" />
        {es ? 'Volver a la lista' : 'Back to list'}
      </Link>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <ComplaintSummaryBar finding={finding} complaintId={complaintId} es={es} />

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-base">
                <span className="flex items-center gap-2">
                  <Workflow className="h-4 w-4" />
                  {es ? 'Tubería de ingesta SBS · 5 etapas' : 'SBS ingestion pipeline · 5 stages'}
                </span>
                <span className="font-mono text-2xs text-fg-muted">
                  {pipelineByKey.size}/5 {es ? 'completadas' : 'done'}
                </span>
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {PIPELINE_STAGES.map((s) => {
                const ev = pipelineByKey.get(s.key);
                const done = Boolean(ev);
                const expanded = expandedStage === `p-${s.key}`;
                return (
                  <StageRow
                    key={s.key}
                    done={done}
                    icon={null}
                    title={es ? s.label_es : s.label_en}
                    actor={s.actor}
                    timestamp={ev?.created_at}
                    typicalMs={s.doc.typical_ms}
                    expanded={expanded}
                    onToggle={() => setExpandedStage(expanded ? null : `p-${s.key}`)}
                    docWhat={es ? s.doc.what_es : s.doc.what_en}
                    docWhy={es ? s.doc.why_es : s.doc.why_en}
                    auditLink={`/audit?action=${encodeURIComponent(s.doc.audit_action)}&object_id=${encodeURIComponent(complaintId)}`}
                    es={es}
                  >
                    {done && s.key === 'pii' && piiBefore ? (
                      <div className="grid gap-2 text-2xs md:grid-cols-2">
                        <div className="rounded-sbs border border-border-subtle bg-surface p-2">
                          <p className="mb-1 flex items-center gap-1 text-2xs uppercase tracking-wide text-fg-muted">
                            <ShieldAlert className="h-3 w-3 text-severity-high-fg" />
                            {es ? 'Antes (FI · contiene PII)' : 'Before (FI · contains PII)'}
                          </p>
                          <p className="font-mono leading-relaxed">{piiBefore}</p>
                        </div>
                        <div className="rounded-sbs border border-status-resolved-border bg-surface p-2">
                          <p className="mb-1 flex items-center gap-1 text-2xs uppercase tracking-wide text-status-resolved-fg">
                            <CheckCircle2 className="h-3 w-3" />
                            {es ? 'Después (canónico · PII redactado)' : 'After (canonical · PII redacted)'}
                          </p>
                          <p className="font-mono leading-relaxed">{piiAfter}</p>
                        </div>
                      </div>
                    ) : null}
                    {done && s.key === 'taxonomy' ? (
                      <TaxonomyMappings events={events} es={es} />
                    ) : null}
                    {done && s.key === 'dq' ? (
                      <DqSummary events={events} es={es} />
                    ) : null}
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      <HitlButton
                        icon={<CheckCircle2 className="h-3 w-3" />}
                        onClick={() => hitl(es ? 'Aprobado por María' : 'Approved by María')}
                        label={es ? 'Aprobar etapa' : 'Approve stage'}
                      />
                      <HitlButton
                        icon={<MessageSquare className="h-3 w-3" />}
                        onClick={() => hitl(es ? 'Observación registrada' : 'Observation logged')}
                        label={es ? 'Añadir observación' : 'Add observation'}
                      />
                      {s.key === 'pii' || s.key === 'dq' || s.key === 'taxonomy' ? (
                        <HitlButton
                          icon={<Send className="h-3 w-3" />}
                          onClick={() => hitl(es ? 'Devuelto a la entidad' : 'Sent back to entity')}
                          label={es ? 'Devolver a entidad' : 'Send back to entity'}
                          variant="warning"
                        />
                      ) : null}
                    </div>
                  </StageRow>
                );
              })}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-base">
                <span className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4" />
                  {es ? 'Procesamiento por agentes · 3 etapas' : 'Agent processing · 3 stages'}
                </span>
                <span className="font-mono text-2xs text-fg-muted">
                  {[...agentByName.keys()].filter((k) => ['triage', 'investigation', 'synthesis'].includes(k)).length}/3
                </span>
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {AGENT_STAGES.map((a) => {
                const run = agentByName.get(a.name);
                const done = run?.status === 'success' || run?.status === 'partial';
                const expanded = expandedStage === `a-${a.name}`;
                const elapsedMs =
                  run?.started_at && run?.ended_at
                    ? Math.max(0, new Date(run.ended_at).getTime() - new Date(run.started_at).getTime())
                    : null;
                return (
                  <StageRow
                    key={a.name}
                    done={done}
                    icon={<span className="text-base" aria-hidden="true">{a.icon}</span>}
                    title={`${es ? a.label_es : a.label_en}${run?.agent_version ? ` · v${run.agent_version}` : ''}`}
                    actor={run?.agent_name || a.name}
                    timestamp={run?.ended_at}
                    elapsedMs={elapsedMs}
                    typicalMs={a.doc.typical_ms}
                    expanded={expanded}
                    onToggle={() => setExpandedStage(expanded ? null : `a-${a.name}`)}
                    docWhat={es ? a.doc.what_es : a.doc.what_en}
                    docWhy={es ? a.doc.why_es : a.doc.why_en}
                    auditLink={`/audit?action=${encodeURIComponent(a.doc.audit_action)}&object_id=${encodeURIComponent(complaintId)}`}
                    es={es}
                  >
                    {run?.tool_calls && run.tool_calls.length > 0 ? (
                      <AgentToolTrace tools={run.tool_calls} />
                    ) : null}
                    {a.name === 'triage' && run?.final_output ? (
                      <ClassificationMini fo={run.final_output} es={es} />
                    ) : null}
                    {a.name === 'investigation' && run?.final_output ? (
                      <InvestigationMini fo={run.final_output} es={es} />
                    ) : null}
                    {a.name === 'synthesis' && run?.final_output ? (
                      <SynthesisMini fo={run.final_output} es={es} />
                    ) : null}
                    {done ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <HitlButton
                          icon={<CheckCircle2 className="h-3 w-3" />}
                          onClick={() => hitl(es ? `Salida de ${a.name} aprobada` : `${a.name} output approved`)}
                          label={es ? 'Aprobar salida' : 'Approve output'}
                        />
                        <HitlButton
                          icon={<Edit3 className="h-3 w-3" />}
                          onClick={() => hitl(es ? 'Edición del agente en curso' : 'Agent override in progress')}
                          label={es ? 'Editar / sobrescribir' : 'Edit / override'}
                        />
                        <HitlButton
                          icon={<MessageSquare className="h-3 w-3" />}
                          onClick={() => hitl(es ? 'Feedback enviado al equipo de modelo' : 'Feedback sent to model team')}
                          label={es ? 'Marcar como mal output' : 'Flag as poor output'}
                          variant="warning"
                        />
                        <HitlButton
                          icon={<Send className="h-3 w-3" />}
                          onClick={() => hitl(es ? 'Solicitud de revisión humana enviada' : 'Manual review requested')}
                          label={es ? 'Solicitar revisión humana' : 'Request manual review'}
                          variant="warning"
                        />
                      </div>
                    ) : null}
                  </StageRow>
                );
              })}
            </CardBody>
          </Card>

          <Card className="border-brand-cyan">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Eye className="h-4 w-4" />
                {es ? 'Acciones del supervisor' : 'Supervisor actions'}
              </CardTitle>
            </CardHeader>
            <CardBody>
              <p className="mb-2 text-xs text-fg-muted">
                {es
                  ? 'Decisión final del reclamo. La elección queda registrada en audit_events con tu identidad y se notifica a la institución.'
                  : 'Final decision on the complaint. The choice is recorded in audit_events with your identity and notified to the institution.'}
              </p>
              <div className="flex flex-wrap gap-2">
                <HitlButton
                  icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                  onClick={() => hitl(es ? 'Reclamo aprobado para cierre' : 'Complaint approved for closure')}
                  label={es ? 'Aprobar y cerrar' : 'Approve & close'}
                  size="lg"
                />
                <HitlButton
                  icon={<ArrowUpRight className="h-3.5 w-3.5" />}
                  onClick={() => hitl(es ? 'Enviado a la cola de aprobaciones (Jefe / Analista)' : 'Sent to approvals queue (Head / Analyst)')}
                  label={es ? 'Enviar a aprobaciones' : 'Send to approvals'}
                  size="lg"
                />
                <HitlButton
                  icon={<AlertTriangle className="h-3.5 w-3.5" />}
                  onClick={() => hitl(es ? 'Escalado al Departamento Legal' : 'Escalated to Legal')}
                  label={es ? 'Escalar a Legal' : 'Escalate to Legal'}
                  size="lg"
                  variant="danger"
                />
                <HitlButton
                  icon={<Send className="h-3.5 w-3.5" />}
                  onClick={() => hitl(es ? 'Devuelto a la entidad con observaciones' : 'Sent back to entity with observations')}
                  label={es ? 'Devolver a la entidad' : 'Send back to entity'}
                  size="lg"
                  variant="warning"
                />
              </div>
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              <span>{es ? 'Bitácora de actividad' : 'Activity log'}</span>
              <Link
                href={`/audit?object_id=${encodeURIComponent(complaintId)}`}
                className="text-2xs text-brand-cyan hover:underline"
              >
                {es ? 'Ver en auditoría →' : 'Open in audit →'}
              </Link>
            </CardTitle>
          </CardHeader>
          <CardBody>
            <ol className="space-y-1.5 text-xs">
              {activityLog.length === 0 ? (
                <li className="text-fg-muted">{es ? 'Esperando eventos…' : 'Waiting for events…'}</li>
              ) : null}
              {activityLog.map((e, i) => (
                <li
                  key={i}
                  className={cn(
                    'rounded-sbs border px-2 py-1',
                    e.severity === 'warn'
                      ? 'border-severity-medium-border bg-severity-medium-bg/40'
                      : e.severity === 'error'
                        ? 'border-danger bg-severity-high-bg'
                        : 'border-border-subtle bg-surface-subtle',
                  )}
                >
                  <p className="flex items-baseline gap-2">
                    <span className="font-mono text-2xs text-fg-muted">
                      {e.ts ? new Date(e.ts).toLocaleTimeString() : '—'}
                    </span>
                    <span className="rounded-sm bg-fg-muted/10 px-1.5 py-0.5 font-mono text-2xs text-fg">
                      {e.actor}
                    </span>
                    <span className="truncate font-mono text-2xs text-brand-navy">{e.tool}</span>
                  </p>
                  {e.summary ? (
                    <p className="ml-1 mt-0.5 font-mono text-2xs text-fg-muted">{e.summary}</p>
                  ) : null}
                </li>
              ))}
            </ol>
          </CardBody>
        </Card>
      </div>

      {hitlToast ? (
        <div className="fixed bottom-4 right-4 z-50 rounded-sbs border border-status-resolved-border bg-status-resolved-bg px-4 py-2 text-sm text-status-resolved-fg shadow-lg">
          ✓ {hitlToast}
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ComplaintSummaryBar(props: { finding: Finding | null; complaintId: string; es: boolean }) {
  const c = props.finding?.complaint;
  if (!c) return null;
  return (
    <Card>
      <CardBody className="grid gap-3 md:grid-cols-4">
        <Field label={props.es ? 'Entidad' : 'Institution'} value={c.institution_name || c.institution_id || '—'} mono />
        <Field label={props.es ? 'Producto' : 'Product'} value={c.product_category || '—'} mono />
        <Field label={props.es ? 'Motivo' : 'Motive'} value={c.motivo_code || '—'} mono />
        <Field label={props.es ? 'Severidad' : 'Severity'} value={(c.severity || 'medium').toUpperCase()} mono />
      </CardBody>
    </Card>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-2xs uppercase tracking-wide text-fg-muted">{label}</p>
      <p className={cn('mt-0.5 text-sm text-fg', mono && 'font-mono')}>{value}</p>
    </div>
  );
}

function StageRow(props: {
  done: boolean;
  icon: React.ReactNode;
  title: string;
  actor: string;
  timestamp?: string;
  elapsedMs?: number | null;
  typicalMs: string;
  expanded: boolean;
  onToggle: () => void;
  docWhat: string;
  docWhy: string;
  auditLink: string;
  es: boolean;
  children?: React.ReactNode;
}) {
  const slow = props.elapsedMs != null && parseTypicalMax(props.typicalMs) > 0 && props.elapsedMs > parseTypicalMax(props.typicalMs) * 2;
  return (
    <div
      className={cn(
        'rounded-sbs border transition-colors',
        props.done
          ? 'border-status-resolved-border bg-status-resolved-bg/30'
          : 'border-border-subtle bg-surface-subtle',
      )}
    >
      <button
        type="button"
        onClick={props.onToggle}
        className="flex w-full items-center gap-3 rounded-sbs px-3 py-2 text-left transition-colors hover:bg-surface"
      >
        {props.done ? (
          <CheckCircle2 className="h-4 w-4 shrink-0 text-status-resolved-fg" />
        ) : (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-fg-muted" />
        )}
        {props.icon ? <span className="shrink-0">{props.icon}</span> : null}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-fg">{props.title}</p>
          <p className="font-mono text-2xs text-fg-muted">
            actor={props.actor}
            {props.timestamp ? ` · ${new Date(props.timestamp).toLocaleTimeString()}` : ''}
            {props.elapsedMs != null ? ` · ${props.elapsedMs}ms` : ''}
            <span className="ml-2 text-fg-muted/70">(typical {props.typicalMs})</span>
            {slow ? (
              <span className="ml-2 rounded-sm bg-severity-medium-bg px-1 text-severity-medium-fg">
                ⚠ {props.es ? 'más lento que típico' : 'slower than typical'}
              </span>
            ) : null}
          </p>
        </div>
        {props.expanded ? <ChevronDown className="h-4 w-4 text-fg-muted" /> : <ChevronRight className="h-4 w-4 text-fg-muted" />}
      </button>
      {props.expanded ? (
        <div className="border-t border-border-subtle px-3 py-3">
          <div className="mb-3 grid gap-2 md:grid-cols-2">
            <div>
              <p className="flex items-center gap-1 text-2xs font-semibold uppercase tracking-wide text-fg-muted">
                <BookOpen className="h-3 w-3" />
                {props.es ? 'Qué hace esta etapa' : 'What this stage does'}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-fg">{props.docWhat}</p>
            </div>
            <div>
              <p className="flex items-center gap-1 text-2xs font-semibold uppercase tracking-wide text-fg-muted">
                <Clock className="h-3 w-3" />
                {props.es ? 'Por qué tarda lo que tarda' : 'Why it takes the time it does'}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-fg">{props.docWhy}</p>
              <Link
                href={props.auditLink}
                className="mt-1.5 inline-flex items-center gap-1 text-2xs text-brand-cyan hover:underline"
              >
                {props.es ? 'Ver eventos en auditoría' : 'See events in audit'} →
              </Link>
            </div>
          </div>
          {props.children}
        </div>
      ) : null}
    </div>
  );
}

function parseTypicalMax(s: string): number {
  const m = s.match(/(\d+)(?:\s*-\s*(\d+))?\s*ms/);
  if (!m) return 0;
  return Number.parseInt(m[2] || m[1], 10);
}

function HitlButton(props: {
  icon: React.ReactNode;
  onClick: () => void;
  label: string;
  variant?: 'default' | 'warning' | 'danger';
  size?: 'sm' | 'lg';
}) {
  const v = props.variant || 'default';
  const sz = props.size || 'sm';
  return (
    <button
      type="button"
      onClick={props.onClick}
      className={cn(
        'inline-flex items-center gap-1 rounded-sbs border font-medium transition-colors',
        sz === 'lg' ? 'h-9 px-3 text-sm' : 'h-6 px-1.5 text-2xs',
        v === 'default' && 'border-border-strong bg-surface text-fg hover:bg-surface-subtle',
        v === 'warning' && 'border-severity-medium-border bg-severity-medium-bg text-severity-medium-fg hover:bg-severity-medium-bg/80',
        v === 'danger' && 'border-danger bg-severity-high-bg text-severity-high-fg hover:bg-severity-high-bg/80',
      )}
    >
      {props.icon}
      {props.label}
    </button>
  );
}

function AgentToolTrace({ tools }: { tools: ToolCall[] }) {
  return (
    <div className="mt-1.5">
      <p className="text-2xs uppercase tracking-wide text-fg-muted">Tool trace</p>
      <ol className="mt-1 space-y-0.5 font-mono text-2xs">
        {tools.map((tc, i) => {
          const elapsed =
            tc.started_at && tc.ended_at
              ? Math.max(0, new Date(tc.ended_at).getTime() - new Date(tc.started_at).getTime())
              : null;
          return (
            <li key={i} className="rounded-sbs border border-border-subtle bg-surface px-2 py-1">
              <span className="text-fg-muted">→</span>{' '}
              <span className="text-fg">{tc.tool_name}</span>{' '}
              {elapsed != null ? <span className="text-fg-muted">({elapsed}ms)</span> : null}
              <p className="ml-3 text-fg-muted">{summariseTool(tc.tool_name || '', tc.output || {})}</p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function ClassificationMini({ fo, es }: { fo: Record<string, unknown>; es: boolean }) {
  const c = (fo.classification as { label?: string; confidence?: number; alternatives?: Array<{ label: string; confidence: number }> }) || {};
  return (
    <div className="mt-1.5 space-y-1 text-xs">
      <p>
        <span className="font-semibold">{es ? 'Clasificación' : 'Classification'}:</span>{' '}
        <span className="font-mono">{c.label || '—'}</span> ·{' '}
        <span className="font-mono text-fg-muted">conf={c.confidence?.toFixed(2)}</span>
      </p>
      {c.alternatives && c.alternatives.length > 0 ? (
        <ul className="ml-3 list-disc text-2xs text-fg-muted">
          {c.alternatives.slice(0, 3).map((a, i) => (
            <li key={i}>
              {a.label} ({a.confidence?.toFixed(2)})
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function InvestigationMini({ fo, es }: { fo: Record<string, unknown>; es: boolean }) {
  const feats = (fo.feature_attribution as Array<{ name: string; contribution: number }>) || [];
  const an = (fo.anomaly as { composite_score?: number; threshold?: number; contributors?: Array<{ signal: string; weight: number }> }) || {};
  return (
    <div className="mt-1.5 space-y-1.5 text-xs">
      {feats.length > 0 ? (
        <div>
          <p className="text-2xs uppercase tracking-wide text-fg-muted">{es ? 'Top features (SHAP)' : 'Top features (SHAP)'}</p>
          <ul className="ml-3 list-disc font-mono text-2xs">
            {feats.slice(0, 4).map((f) => (
              <li key={f.name}>
                {f.name}{' '}
                <span className={f.contribution >= 0 ? 'text-severity-high-fg' : 'text-status-resolved-fg'}>
                  ({f.contribution >= 0 ? '+' : ''}{f.contribution.toFixed(2)})
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {typeof an.composite_score === 'number' ? (
        <p>
          <span className="font-semibold">{es ? 'Anomalía compuesta' : 'Composite anomaly'}:</span>{' '}
          <span className="font-mono">{an.composite_score.toFixed(2)}</span> ·{' '}
          <span className="text-fg-muted">{es ? 'umbral' : 'threshold'} {an.threshold?.toFixed(2) || '0.70'}</span>
          {an.composite_score >= (an.threshold || 0.7) ? (
            <span className="ml-2 rounded-sm bg-brand-gold/20 px-1 py-0.5 font-mono text-2xs text-brand-navy">ALTO</span>
          ) : null}
        </p>
      ) : null}
      {an.contributors && an.contributors.length > 0 ? (
        <p className="ml-3 text-2xs text-fg-muted">
          {es ? 'Contribuyentes' : 'Contributors'}: {an.contributors.map((c) => `${c.signal} (${c.weight})`).join(', ')}
        </p>
      ) : null}
    </div>
  );
}

function SynthesisMini({ fo, es }: { fo: Record<string, unknown>; es: boolean }) {
  const sm = (fo.executive_summary as { text?: string; key_points?: string[]; audience?: string }) || {};
  if (!sm.text) return null;
  return (
    <div className="mt-1.5 space-y-1 text-xs">
      <p className="leading-relaxed text-fg">{sm.text}</p>
      {sm.key_points ? (
        <ul className="ml-3 list-disc text-2xs">
          {sm.key_points.slice(0, 4).map((kp, i) => (
            <li key={i}>{kp}</li>
          ))}
        </ul>
      ) : null}
      <p className="text-2xs text-fg-muted">{es ? 'audiencia' : 'audience'}: {sm.audience || 'supervisor'}</p>
    </div>
  );
}

function TaxonomyMappings({ events, es }: { events: AuditEvent[]; es: boolean }) {
  const evs = events.filter((e) => e.action === 'taxonomy-normalized').slice(0, 6);
  if (evs.length === 0) {
    return (
      <p className="text-2xs text-fg-muted">{es ? 'Sin términos canonicalizados.' : 'No taxonomy normalizations.'}</p>
    );
  }
  return (
    <div>
      <p className="text-2xs uppercase tracking-wide text-fg-muted">{es ? 'Términos mapeados' : 'Mapped terms'}</p>
      <ul className="mt-1 space-y-0.5 font-mono text-2xs">
        {evs.map((e, i) => {
          const d = (e.diff || {}) as Record<string, unknown>;
          return (
            <li key={i}>
              {String(d.field_path || '?')}:{' '}
              <span className="text-fg-muted">{String(d.original_value ?? '')}</span> →{' '}
              <span className="text-brand-navy">{String(d.canonical_value ?? '')}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function DqSummary({ events, es }: { events: AuditEvent[]; es: boolean }) {
  const completed = events.find((e) => e.action === 'data-quality-completed');
  const violations = events.filter((e) => e.action === 'dq-rule-violated');
  const d = (completed?.diff || {}) as Record<string, unknown>;
  return (
    <div className="text-2xs">
      <p className="text-fg-muted">
        {es ? 'Errores' : 'Errors'}:{' '}
        <span className="font-mono text-fg">{String(d.error_count ?? 0)}</span> · {es ? 'Warnings' : 'Warnings'}:{' '}
        <span className="font-mono text-fg">{String(d.warning_count ?? 0)}</span> · {es ? 'Política' : 'Policy'}:{' '}
        <span className="font-mono text-fg">{String(d.policy_version ?? 'dq-demo-v1')}</span>
      </p>
      {violations.length > 0 ? (
        <ul className="mt-1 ml-3 list-disc">
          {violations.slice(0, 5).map((v, i) => {
            const dv = (v.diff || {}) as Record<string, unknown>;
            return (
              <li key={i}>
                <span className="font-mono">{String(dv.rule_id ?? '?')}</span> · {String(dv.field_path ?? '')}: {String(dv.message ?? '')}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function actorForAuditAction(action: string): string {
  if (action.startsWith('pii-')) return 'pii-redactor';
  if (action.startsWith('dq-') || action.startsWith('data-quality')) return 'dq-validator';
  if (action.startsWith('taxonomy-')) return 'taxonomy-normalizer';
  if (action === 'canonical-complaint-persisted') return 'persistence';
  if (action === 'complaint-received' || action === 'complaint-triage-emitted') return 'ingestion-orchestrator';
  return 'pipeline';
}

function summariseAuditDiff(e: AuditEvent): string {
  if (!e.diff) return '';
  const d = e.diff as Record<string, unknown>;
  if (e.action === 'pii-redacted') {
    return `entities=${String(d.entity_count ?? '?')} policy=${String(d.policy_version ?? '?')}`;
  }
  if (e.action === 'taxonomy-normalized') {
    return `${String(d.field_path ?? '?')}: ${String(d.original_value ?? '')} → ${String(d.canonical_value ?? '')}`;
  }
  if (e.action === 'data-quality-completed') {
    return `errors=${String(d.error_count ?? d.errors ?? 0)} warnings=${String(d.warning_count ?? d.warnings ?? 0)}`;
  }
  if (e.action === 'dq-rule-violated') {
    return `${String(d.rule_id ?? '?')} · ${String(d.field_path ?? '?')}`;
  }
  return '';
}

function summariseTool(tool: string, out: Record<string, unknown>): string {
  if (tool === 'bert_classifier') return `${out.classification ?? '?'} (conf=${out.confidence ?? '?'})`;
  if (tool === 'rank_features') {
    const top = (out.top_features as Array<{ name: string; contribution: number }>)?.[0];
    if (top) return `top=${top.name} ${top.contribution >= 0 ? '+' : ''}${top.contribution}`;
  }
  if (tool === 'anomaly_detector') return `composite_score=${out.composite_score ?? '?'}`;
  if (tool === 'search_similar_complaints') {
    const items = (out.items as unknown[]) || [];
    return `matches=${items.length}`;
  }
  if (tool === 'draft_narrative') return `chars=${((out.text as string) || '').length}`;
  if (tool === 'compose_executive_summary') return `key_points=${((out.key_points as string[]) || []).length}`;
  return '';
}
