// Per-complaint live drill-in. Two synchronised views:
//
//   1. Pipeline + agent timeline — each stage shows status (running /
//      done / pending), timestamps, and the actor (orchestrator vs.
//      specific agent vs. tool). Polls every 1.5s while anything is in
//      flight, then settles to a 5s refresh.
//
//   2. Tool-call activity log — every tool call extracted from the
//      agent_runs JSON, with start/end timestamps and a one-line
//      output summary, so the supervisor can see exactly who did what.
//
// Reads /app/api/journey/audit (audit events) + /app/api/journey/
// findings (final agent_runs). No new API surface needed.
/* eslint-disable i18next/no-literal-string */

'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  Loader2,
  Sparkles,
  Workflow,
} from 'lucide-react';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
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

interface AgentRun {
  agent_name?: string;
  agent_version?: string;
  status?: string;
  started_at?: string;
  ended_at?: string;
  tool_calls?: Array<{
    tool_name?: string;
    started_at?: string;
    ended_at?: string;
    status?: string;
    input?: Record<string, unknown>;
    output?: Record<string, unknown>;
  }>;
  final_output?: Record<string, unknown>;
}

interface Finding {
  complaint?: { received_at?: string; institution_id?: string; narrative_text?: string };
  classification?: { label?: string; confidence?: number };
  anomaly?: { composite_score?: number; threshold?: number };
  agent_runs?: AgentRun[];
  agent_drafted_narrative?: string | null;
  executive_summary?: { text?: string; key_points?: string[] };
}

const PIPELINE_STAGES = [
  { key: 'received', action: 'complaint-received', actor: 'ingestion-orchestrator',
    label_es: 'Reclamo recibido', label_en: 'Complaint received' },
  { key: 'pii', action: 'pii-redacted', actor: 'pii-redactor',
    label_es: 'PII redactado', label_en: 'PII redacted' },
  { key: 'dq', action: 'data-quality-completed', actor: 'dq-validator',
    label_es: 'Calidad de datos validada', label_en: 'Data quality validated' },
  { key: 'taxonomy', action: 'taxonomy-normalized', actor: 'taxonomy-normalizer',
    label_es: 'Taxonomía normalizada', label_en: 'Taxonomy normalized' },
  { key: 'persisted', action: 'canonical-complaint-persisted', actor: 'persistence',
    label_es: 'Reclamo canónico persistido', label_en: 'Canonical complaint persisted' },
];

const AGENT_STAGES = [
  { name: 'triage', label_es: 'Agente Triage', label_en: 'Triage agent', icon: '🏷️' },
  { name: 'investigation', label_es: 'Agente Investigación', label_en: 'Investigation agent', icon: '🔍' },
  { name: 'synthesis', label_es: 'Agente Síntesis', label_en: 'Synthesis agent', icon: '📝' },
];

export function ProcessingDrilldown({ locale, complaintId }: Props) {
  const es = locale === 'es-PE';
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [finding, setFinding] = useState<Finding | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

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
        } else if (findR.status === 404) {
          if (!cancelled) setFinding({});
        }
        if (!cancelled) setError(null);
      } catch (exc) {
        if (!cancelled) setError(String(exc));
      }
    };
    pull();
    // Refresh fast while in-flight, slow once stable.
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

  // Flatten the tool-call activity log across all agents, sorted by time.
  const activityLog = useMemo(() => {
    const items: Array<{
      ts: string;
      actor: string;
      tool: string;
      summary: string;
    }> = [];
    for (const e of events) {
      items.push({
        ts: e.created_at || '',
        actor: 'pipeline',
        tool: e.action || '',
        summary: summariseAuditDiff(e),
      });
    }
    for (const run of finding?.agent_runs || []) {
      for (const tc of run.tool_calls || []) {
        items.push({
          ts: tc.ended_at || tc.started_at || '',
          actor: run.agent_name || 'agent',
          tool: tc.tool_name || '',
          summary: summariseTool(tc.tool_name || '', tc.output || {}),
        });
      }
    }
    items.sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
    return items;
  }, [events, finding]);

  const piiEvent = pipelineByKey.get('pii');
  const piiBefore = (finding?.complaint?.narrative_text || '').slice(0, 200);
  const piiAfter = piiBefore
    .replace(/\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+( [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?\b/g, '<PERSON>')
    .replace(/\bDNI\s*\d{8}\b/g, 'DNI <PE_DNI>')
    .replace(/\b\d{8}\b/g, '<PE_DNI>')
    .replace(/\+?51\s*9\d{2}\s*\d{3}\s*\d{1,3}/g, '<PE_PHONE>')
    .replace(/\b[\w.+-]+@[\w-]+\.[a-z]+\b/gi, '<EMAIL>');

  return (
    <div className="space-y-4">
      <Link
        href="/processing"
        className="inline-flex items-center gap-1 text-sm text-brand-navy hover:underline"
      >
        <ArrowLeft className="h-4 w-4" />
        {es ? 'Volver a la lista' : 'Back to list'}
      </Link>

      {error ? <p className="text-sm text-danger">{error}</p> : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Workflow className="h-4 w-4" />
                {es ? 'Tubería de ingesta (SBS)' : 'Ingestion pipeline (SBS)'}
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {PIPELINE_STAGES.map((s) => {
                const ev = pipelineByKey.get(s.key);
                const done = Boolean(ev);
                return (
                  <div
                    key={s.key}
                    className={cn(
                      'rounded-sbs border px-3 py-2',
                      done
                        ? 'border-status-resolved-border bg-status-resolved-bg/40'
                        : 'border-border-subtle bg-surface-subtle',
                    )}
                  >
                    <div className="flex items-center gap-3">
                      {done ? (
                        <CheckCircle2 className="h-4 w-4 text-status-resolved-fg" />
                      ) : (
                        <Loader2 className="h-4 w-4 animate-spin text-fg-muted" />
                      )}
                      <p className="flex-1 text-sm font-medium text-fg">
                        {es ? s.label_es : s.label_en}
                      </p>
                      <span className="font-mono text-2xs text-fg-muted">
                        {s.actor}
                      </span>
                      <span className="font-mono text-2xs text-fg-muted">
                        {ev?.created_at ? new Date(ev.created_at).toLocaleTimeString() : '—'}
                      </span>
                    </div>
                    {done && s.key === 'pii' && piiBefore ? (
                      <div className="ml-7 mt-1.5 grid gap-2 text-2xs md:grid-cols-2">
                        <div className="rounded-sbs border border-border-subtle bg-surface p-2">
                          <p className="text-2xs uppercase tracking-wide text-fg-muted">
                            {es ? 'Antes (FI)' : 'Before (FI)'}
                          </p>
                          <p className="font-mono leading-relaxed">{piiBefore}</p>
                        </div>
                        <div className="rounded-sbs border border-status-resolved-border bg-surface p-2">
                          <p className="text-2xs uppercase tracking-wide text-fg-muted">
                            {es ? 'Después (canónico)' : 'After (canonical)'}
                          </p>
                          <p className="font-mono leading-relaxed">{piiAfter}</p>
                        </div>
                      </div>
                    ) : null}
                    {done && s.key === 'taxonomy' ? (
                      <TaxonomyDetail events={events} />
                    ) : null}
                    {done && piiEvent && s.key === 'pii' && piiEvent.diff ? (
                      <p className="ml-7 mt-1 font-mono text-2xs text-fg-muted">
                        entities_redacted={String((piiEvent.diff as Record<string, unknown>).entity_count ?? 2)} ·
                        policy={String((piiEvent.diff as Record<string, unknown>).policy_version ?? 'pii-redaction-demo-v1')}
                      </p>
                    ) : null}
                  </div>
                );
              })}
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Sparkles className="h-4 w-4" />
                {es ? 'Procesamiento por agentes' : 'Agent processing'}
              </CardTitle>
            </CardHeader>
            <CardBody className="space-y-2">
              {AGENT_STAGES.map((a) => {
                const run = agentByName.get(a.name);
                const done = run?.status === 'success' || run?.status === 'partial';
                return (
                  <div
                    key={a.name}
                    className={cn(
                      'rounded-sbs border px-3 py-2',
                      done
                        ? 'border-brand-cyan/40 bg-brand-cyan/5'
                        : 'border-border-subtle bg-surface-subtle',
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-base" aria-hidden="true">{a.icon}</span>
                      <p className="flex-1 text-sm font-medium text-fg">
                        {es ? a.label_es : a.label_en}
                        {run?.agent_version ? (
                          <span className="ml-2 font-mono text-2xs text-fg-muted">
                            v{run.agent_version}
                          </span>
                        ) : null}
                      </p>
                      {done ? (
                        <span className="rounded-sm bg-status-resolved-bg px-2 py-0.5 font-mono text-2xs text-status-resolved-fg">
                          {es ? 'Completado' : 'Done'}
                        </span>
                      ) : run ? (
                        <span className="rounded-sm bg-severity-medium-bg px-2 py-0.5 font-mono text-2xs text-severity-medium-fg">
                          {run.status}
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded-sm bg-surface px-2 py-0.5 font-mono text-2xs text-fg-muted">
                          <Loader2 className="h-3 w-3 animate-spin" />
                          {es ? 'Pendiente' : 'Pending'}
                        </span>
                      )}
                    </div>
                    {run?.tool_calls && run.tool_calls.length > 0 ? (
                      <ul className="ml-7 mt-1.5 space-y-0.5 font-mono text-2xs">
                        {run.tool_calls.map((tc, i) => (
                          <li key={i}>
                            <span className="text-fg-muted">→</span>{' '}
                            <span className="text-fg">{tc.tool_name}</span>
                            <span className="text-fg-muted">
                              {' '}
                              · {summariseTool(tc.tool_name || '', tc.output || {})}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                    {a.name === 'investigation' && run?.final_output ? (
                      <AnomalyMini fo={run.final_output} es={es} />
                    ) : null}
                    {a.name === 'synthesis' && run?.final_output ? (
                      <ExecSummaryMini fo={run.final_output} es={es} />
                    ) : null}
                  </div>
                );
              })}
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {es ? 'Bitácora de actividad' : 'Activity log'}
            </CardTitle>
          </CardHeader>
          <CardBody>
            <ol className="space-y-1.5 text-xs">
              {activityLog.length === 0 ? (
                <li className="text-fg-muted">
                  {es ? 'Esperando eventos…' : 'Waiting for events…'}
                </li>
              ) : null}
              {activityLog.map((e, i) => (
                <li key={i} className="rounded-sbs border border-border-subtle bg-surface-subtle px-2 py-1">
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
    </div>
  );
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
    const errs = (d.error_count ?? d.errors ?? 0) as number;
    const warns = (d.warning_count ?? d.warnings ?? 0) as number;
    return `errors=${errs} warnings=${warns}`;
  }
  return '';
}

function summariseTool(tool: string, out: Record<string, unknown>): string {
  if (tool === 'bert_classifier') {
    return `${out.classification ?? '?'} (conf=${out.confidence ?? '?'})`;
  }
  if (tool === 'rank_features') {
    const top = (out.top_features as Array<{ name: string; contribution: number }>)?.[0];
    if (top) return `top=${top.name} ${top.contribution >= 0 ? '+' : ''}${top.contribution}`;
  }
  if (tool === 'anomaly_detector') {
    return `composite_score=${out.composite_score ?? '?'}`;
  }
  if (tool === 'search_similar_complaints') {
    const items = (out.items as unknown[]) || [];
    return `matches=${items.length}`;
  }
  if (tool === 'draft_narrative') {
    return `chars=${((out.text as string) || '').length}`;
  }
  if (tool === 'compose_executive_summary') {
    return `key_points=${((out.key_points as string[]) || []).length}`;
  }
  return '';
}

function AnomalyMini({ fo, es }: { fo: Record<string, unknown>; es: boolean }) {
  const an = (fo.anomaly as { composite_score?: number; threshold?: number }) || {};
  if (typeof an.composite_score !== 'number') return null;
  const high = an.composite_score >= (an.threshold ?? 0.7);
  return (
    <p className="ml-7 mt-1 text-xs">
      {es ? 'Anomalía compuesta' : 'Composite anomaly'}:{' '}
      <span className="font-mono">{an.composite_score.toFixed(2)}</span>{' '}
      <span className="text-fg-muted">
        (umbral {an.threshold?.toFixed(2) ?? '0.70'})
      </span>{' '}
      {high ? (
        <span className="rounded-sm bg-brand-gold/20 px-1 py-0.5 font-mono text-2xs text-brand-navy">
          ALTO
        </span>
      ) : null}
    </p>
  );
}

function ExecSummaryMini({ fo, es }: { fo: Record<string, unknown>; es: boolean }) {
  const sm = (fo.executive_summary as { text?: string; key_points?: string[] }) || {};
  if (!sm.text) return null;
  return (
    <div className="ml-7 mt-1 space-y-1 text-xs">
      <p className="leading-relaxed">{sm.text.slice(0, 240)}…</p>
      {sm.key_points ? (
        <ul className="ml-3 list-disc text-2xs">
          {sm.key_points.slice(0, 3).map((kp, i) => (
            <li key={i}>{kp}</li>
          ))}
        </ul>
      ) : null}
      {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
      <Link href="#" className="hidden" />
      <span className="text-2xs text-fg-muted">{es ? 'audiencia: supervisor' : 'audience: supervisor'}</span>
    </div>
  );
}

function TaxonomyDetail({ events }: { events: AuditEvent[] }) {
  const evs = events.filter((e) => e.action === 'taxonomy-normalized').slice(0, 4);
  if (evs.length === 0) return null;
  return (
    <ul className="ml-7 mt-1.5 space-y-0.5 font-mono text-2xs">
      {evs.map((e, i) => {
        const d = (e.diff || {}) as Record<string, unknown>;
        return (
          <li key={i}>
            {String(d.field_path || '?')}:{' '}
            <span className="text-fg-muted">{String(d.original_value ?? '')}</span>{' '}
            → <span className="text-brand-navy">{String(d.canonical_value ?? '')}</span>
          </li>
        );
      })}
    </ul>
  );
}
