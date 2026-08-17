// SPDX-License-Identifier: Apache-2.0
// SBS-side demo journey. Drives three stages on a single complaint:
//
//   1. Recepción SBS — pipeline de ingesta (audit-event poll)
//   2. Procesamiento agéntico — five agent cards (triage, investigation,
//      synthesis LIVE; cockpit-monitor, insights REPLAY)
//   3. Cabina del supervisor — handoff with anomaly summary + two CTAs
//
// LIVE agents read from /app/api/journey/findings (which proxies the
// internal FastAPI findings endpoint). REPLAY agents render a
// pre-generated card so the demo always shows the full 5-agent flow.
//
// i18next literal-string check disabled in this file: most strings are
// agent-protocol labels, technical IDs, and timestamps.
/* eslint-disable i18next/no-literal-string */

'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  ChevronRight,
  Loader2,
  Sparkles,
  Workflow,
} from 'lucide-react';

import { Badge, Button, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

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
  id?: string;
  agent_name?: string;
  agent_version?: string;
  status?: string;
  started_at?: string;
  ended_at?: string;
  tool_calls?: ToolCall[];
  final_output?: Record<string, unknown>;
}

interface FindingPayload {
  classification?: { label?: string; confidence?: number };
  features?: { feature_contributions?: Array<{ feature_name: string; contribution: number }> };
  anomaly?: { composite_score?: number; threshold?: number; contributors?: Array<{ signal: string; weight: number }> };
  executive_summary?: { text?: string; key_points?: string[] };
  agent_drafted_narrative?: string | null;
  agent_runs?: AgentRun[];
}

interface Props {
  locale: Locale;
  complaintId: string;
}

const PIPELINE_STEPS = [
  { key: 'received', action: 'complaint-received', label_es: 'Reclamo recibido', label_en: 'Complaint received' },
  { key: 'redacted', action: 'pii-redacted', label_es: 'PII anonimizado', label_en: 'PII anonymized' },
  { key: 'dq', action: 'data-quality-completed', label_es: 'Calidad de datos validada', label_en: 'Data quality validated' },
  { key: 'taxonomy', action: 'taxonomy-normalized', label_es: 'Taxonomía normalizada', label_en: 'Taxonomy normalized' },
  { key: 'persisted', action: 'canonical-complaint-persisted', label_es: 'Reclamo canónico persistido', label_en: 'Canonical complaint persisted' },
];

export function DemoJourneySbs({ locale, complaintId }: Props) {
  const es = locale === 'es-PE';

  // --- Stage 1: audit poll --------------------------------------------------
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [pipelineHits, setPipelineHits] = useState<Set<string>>(new Set());
  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    const poll = async () => {
      if (cancelled) return;
      attempts += 1;
      try {
        const r = await fetch(
          `/app/api/journey/audit?object_id=${encodeURIComponent(complaintId)}`,
          { cache: 'no-store' },
        );
        if (r.ok) {
          const json = (await r.json()) as { events?: AuditEvent[] };
          const evs = json.events || [];
          setEvents(evs);
          const hits = new Set<string>();
          for (const e of evs) {
            const a = (e.action || '').toString();
            for (const s of PIPELINE_STEPS) {
              if (a === s.action) hits.add(s.key);
            }
          }
          setPipelineHits(hits);
          if (hits.size >= 5) return;
        }
      } catch {
        // keep polling
      }
      if (attempts < 30) setTimeout(poll, 500);
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [complaintId]);

  // --- Stage 2: findings + agents -------------------------------------------
  const [finding, setFinding] = useState<FindingPayload | null>(null);
  const [findingError, setFindingError] = useState<string | null>(null);
  useEffect(() => {
    if (pipelineHits.size < 4) return;
    let cancelled = false;
    let attempts = 0;
    const poll = async () => {
      if (cancelled) return;
      attempts += 1;
      try {
        const r = await fetch(
          `/app/api/journey/findings?complaint_id=${encodeURIComponent(complaintId)}`,
          { cache: 'no-store' },
        );
        if (r.ok) {
          const json = (await r.json()) as FindingPayload;
          setFinding(json);
          return;
        }
        if (r.status === 404 && attempts >= 4) {
          setFindingError('finding-not-found');
          return;
        }
      } catch {
        // ignore
      }
      if (attempts < 12) setTimeout(poll, 800);
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [complaintId, pipelineHits.size]);

  const agentByName = useMemo(() => {
    const map = new Map<string, AgentRun>();
    for (const run of finding?.agent_runs || []) {
      if (run.agent_name) map.set(run.agent_name, run);
    }
    return map;
  }, [finding]);

  // Reveal agent cards sequentially for visual rhythm.
  const [agentRevealed, setAgentRevealed] = useState(0);
  useEffect(() => {
    if (!finding) return;
    setAgentRevealed(0);
    const timers: ReturnType<typeof setTimeout>[] = [];
    for (let i = 1; i <= 5; i++) {
      timers.push(setTimeout(() => setAgentRevealed(i), 1500 * i));
    }
    return () => timers.forEach((t) => clearTimeout(t));
  }, [finding]);

  const anomalyScore = finding?.anomaly?.composite_score ?? null;
  const anomalyThresh = finding?.anomaly?.threshold ?? 0.7;
  const anomalyHigh = anomalyScore !== null && anomalyScore >= anomalyThresh;

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 px-6 py-6">
      <header>
        <h1 className="text-2xl font-semibold text-brand-navy">
          {es ? 'Recorrido del reclamo en SBS' : 'Complaint journey at SBS'}
        </h1>
        <p className="text-sm text-fg-muted">
          {es
            ? 'Trazabilidad completa desde la recepción del reclamo hasta la cabina del supervisor.'
            : 'End-to-end trace from intake to the supervisor cockpit.'}{' '}
          <span className="font-mono text-xs text-brand-navy">
            complaint_id={complaintId}
          </span>
        </p>
      </header>

      {/* Stage 1 — Pipeline */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-brand-navy">
          <Workflow className="h-5 w-5" />
          {es ? '1 · Recepción SBS · Pipeline de ingesta' : '1 · SBS receive · Ingestion pipeline'}
        </h2>
        <Card>
          <CardBody className="space-y-2">
            {PIPELINE_STEPS.map((s) => {
              const done = pipelineHits.has(s.key);
              return (
                <div key={s.key}>
                  <div
                    className={cn(
                      'flex items-center gap-3 rounded-sbs border px-3 py-2',
                      done
                        ? 'border-status-resolved-border bg-status-resolved-bg/40'
                        : 'border-border-subtle bg-surface-subtle',
                    )}
                  >
                    {done ? (
                      <CheckCircle2 className="h-5 w-5 shrink-0 text-status-resolved-fg" />
                    ) : (
                      <Loader2 className="h-5 w-5 shrink-0 animate-spin text-fg-muted" />
                    )}
                    <p className="text-sm font-medium text-fg">
                      {es ? s.label_es : s.label_en}
                    </p>
                    <span className="ml-auto font-mono text-2xs text-fg-muted">
                      {s.action}
                    </span>
                  </div>
                  {done && s.key === 'redacted' ? (
                    <PipelineDetail kind="redaction" events={events} es={es} />
                  ) : null}
                  {done && s.key === 'taxonomy' ? (
                    <PipelineDetail kind="taxonomy" events={events} es={es} />
                  ) : null}
                  {done && s.key === 'dq' ? (
                    <PipelineDetail kind="dq" events={events} es={es} />
                  ) : null}
                </div>
              );
            })}
          </CardBody>
        </Card>
      </section>

      {/* Stage 2 — Agents */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-brand-navy">
          <Sparkles className="h-5 w-5" />
          {es ? '2 · Procesamiento agéntico' : '2 · Agent processing'}
        </h2>

        {findingError ? (
          <Card className="border-danger">
            <CardBody className="text-sm text-danger">
              {es
                ? 'No se encontró el hallazgo para este reclamo. Verifica que el agent_runs esté sembrado.'
                : 'No finding found for this complaint. Check that agent_runs is seeded.'}
            </CardBody>
          </Card>
        ) : null}

        {!finding && !findingError ? (
          <Card>
            <CardBody className="flex items-center gap-2 text-sm text-fg-muted">
              <Loader2 className="h-4 w-4 animate-spin" />
              {es
                ? 'Esperando que termine la tubería de ingesta…'
                : 'Waiting for the ingestion pipeline to finish…'}
            </CardBody>
          </Card>
        ) : null}

        {finding ? (
          <ol className="space-y-3">
            {agentRevealed >= 1 ? (
              <li>
                <AgentCard
                  liveOrReplay="live"
                  name="triage"
                  run={agentByName.get('triage')}
                  es={es}
                  body={(run) => (
                    <TriageBody run={run} fallback={finding} es={es} />
                  )}
                />
              </li>
            ) : null}
            {agentRevealed >= 2 ? (
              <li>
                <AgentCard
                  liveOrReplay="live"
                  name="investigation"
                  run={agentByName.get('investigation')}
                  es={es}
                  body={(run) => (
                    <InvestigationBody
                      run={run}
                      fallback={finding}
                      es={es}
                    />
                  )}
                />
              </li>
            ) : null}
            {agentRevealed >= 3 ? (
              <li>
                <AgentCard
                  liveOrReplay="live"
                  name="synthesis"
                  run={agentByName.get('synthesis')}
                  es={es}
                  body={(run) => (
                    <SynthesisBody run={run} fallback={finding} es={es} />
                  )}
                />
              </li>
            ) : null}
            {agentRevealed >= 4 ? (
              <li>
                <ReplayAgentCard
                  name="cockpit-monitor"
                  versionLabel="0.1.0"
                  es={es}
                  outputTitle={es ? 'Salida' : 'Output'}
                  output={
                    <ul className="text-xs leading-relaxed text-fg">
                      <li>
                        ↑ {es ? 'KPI · reclamos en últimas 24h' : 'KPI · complaints last 24h'}: 47 (+12% wow)
                      </li>
                      <li>
                        ⚠ {es ? 'Anomalía publicada en panel principal' : 'Anomaly published to main panel'} ({anomalyScore?.toFixed(2) ?? '0.74'})
                      </li>
                      <li>
                        ✉ {es ? 'Notificación push a Supervisor (supervisora)' : 'Push notification to Supervisor (supervisor)'}
                      </li>
                    </ul>
                  }
                  toolCalls={[
                    'publish_cockpit_event(topic="anomaly.new", score=0.74)',
                    'increment_kpi("complaints_24h")',
                    'notify_persona("supervisor", priority="HIGH")',
                  ]}
                />
              </li>
            ) : null}
            {agentRevealed >= 5 ? (
              <li>
                <ReplayAgentCard
                  name="insights"
                  versionLabel="0.1.0"
                  es={es}
                  outputTitle={es ? 'Salida' : 'Output'}
                  output={
                    <ul className="text-xs leading-relaxed text-fg">
                      <li>
                        {es
                          ? 'Patrón detectado: comisiones por mantenimiento omitidas en la narrativa del agente'
                          : 'Pattern detected: maintenance fees omitted from the agent narrative'}
                      </li>
                      <li>
                        {es
                          ? 'Coincidencia con 3 reclamos similares (similitud > 0.84)'
                          : 'Match with 3 similar complaints (similarity > 0.84)'}
                      </li>
                      <li>
                        {es
                          ? 'Recomendación para Superintendent (cumplimiento): revisar cláusulas contractuales BANCO_DEMO_001'
                          : 'Recommendation for Superintendent (compliance): review BANCO_DEMO_001 contract clauses'}
                      </li>
                    </ul>
                  }
                  toolCalls={[
                    'aggregate_similar_complaints(window=30d)',
                    'extract_omission_pattern("comisión por mantenimiento")',
                    'recommend_followup(persona="superintendent")',
                  ]}
                />
              </li>
            ) : null}
          </ol>
        ) : null}
      </section>

      {/* Stage 3 — Handoff */}
      {agentRevealed >= 5 ? (
        <section className="space-y-3">
          <h2 className="flex items-center gap-2 text-lg font-semibold text-brand-navy">
            <ChevronRight className="h-5 w-5" />
            {es ? '3 · Cabina del supervisor' : '3 · Supervisor cockpit'}
          </h2>
          <Card className={cn('border-2', anomalyHigh ? 'border-brand-gold' : 'border-brand-cyan')}>
            <CardBody className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-sm">
                  <span className="font-semibold">
                    {es ? 'Anomalía compuesta:' : 'Composite anomaly:'}{' '}
                  </span>
                  <span className="font-mono">
                    {anomalyScore?.toFixed(2) ?? '—'}
                  </span>{' '}
                  ·{' '}
                  <span className="text-fg-muted">
                    {es ? 'Umbral:' : 'Threshold:'} {anomalyThresh.toFixed(2)}
                  </span>{' '}
                  ·{' '}
                  <span
                    className={cn(
                      'rounded-sm px-2 py-0.5 text-xs font-semibold',
                      anomalyHigh
                        ? 'bg-brand-gold/20 text-brand-navy'
                        : 'bg-status-resolved-bg text-status-resolved-fg',
                    )}
                  >
                    {anomalyHigh ? 'ALTO' : 'OK'}
                  </span>
                </p>
                <p className="mt-1 text-xs text-fg-muted">
                  {es
                    ? 'El reclamo está listo para revisión humana en la cabina del supervisor.'
                    : 'The complaint is ready for human review in the cockpit.'}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link
                  href="/cockpit"
                  className="inline-flex h-9 items-center rounded-sbs bg-brand-navy px-4 text-sm font-medium text-fg-inverted hover:bg-brand-navy/90"
                >
                  {es ? 'Ver en cabina' : 'Open cockpit'}
                </Link>
                <Link
                  href={`/findings/${complaintId}`}
                  className="inline-flex h-9 items-center rounded-sbs border border-border-strong bg-surface px-4 text-sm font-medium text-fg hover:bg-surface-subtle"
                >
                  {es ? 'Ver hallazgo detallado' : 'Open finding detail'}
                </Link>
              </div>
            </CardBody>
          </Card>
        </section>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PipelineDetail(props: {
  kind: 'redaction' | 'dq' | 'taxonomy';
  events: AuditEvent[];
  es: boolean;
}) {
  if (props.kind === 'redaction') {
    const ev = props.events.find((e) => e.action === 'pii-redacted');
    const diff = (ev?.diff || {}) as Record<string, unknown>;
    const count = (diff.entity_count as number) || (diff.entities as number) || 2;
    return (
      <div className="ml-8 mt-1.5 grid grid-cols-1 gap-2 text-xs md:grid-cols-2">
        <div className="rounded-sbs border border-border-subtle bg-surface px-2 py-1">
          <p className="text-2xs uppercase tracking-wide text-fg-muted">
            {props.es ? 'Antes' : 'Before'}
          </p>
          <p className="font-mono">
            Cliente Carlos Rodríguez Mendoza (DNI 12345678)…
          </p>
        </div>
        <div className="rounded-sbs border border-status-resolved-border bg-surface px-2 py-1">
          <p className="text-2xs uppercase tracking-wide text-fg-muted">
            {props.es ? 'Después' : 'After'}
          </p>
          <p className="font-mono">
            Cliente &lt;PERSON&gt; (&lt;PE_DNI&gt;)…
          </p>
          <p className="mt-1 text-2xs text-fg-muted">entidades redactadas: {count}</p>
        </div>
      </div>
    );
  }
  if (props.kind === 'taxonomy') {
    const evs = props.events.filter((e) => e.action === 'taxonomy-normalized');
    const items = evs
      .map((e) => (e.diff || {}) as Record<string, unknown>)
      .slice(0, 6);
    if (items.length === 0) return null;
    return (
      <div className="ml-8 mt-1.5">
        <p className="text-2xs uppercase tracking-wide text-fg-muted">
          {props.es ? 'Términos mapeados' : 'Mapped terms'}
        </p>
        <ul className="space-y-0.5 text-xs">
          {items.map((d, i) => (
            <li key={i} className="font-mono">
              {String(d.field_path || '?')}:{' '}
              <span className="text-fg-muted">
                {String(d.original_value ?? '')}
              </span>{' '}
              →{' '}
              <span className="text-brand-navy">
                {String(d.canonical_value ?? '')}
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  if (props.kind === 'dq') {
    const ev = props.events.find((e) => e.action === 'data-quality-completed');
    const diff = (ev?.diff || {}) as Record<string, unknown>;
    return (
      <pre className="ml-8 mt-1.5 max-h-32 overflow-auto rounded-sbs border border-border-subtle bg-surface px-2 py-1 text-2xs">
        {JSON.stringify(diff, null, 2).slice(0, 600)}
      </pre>
    );
  }
  return null;
}

function AgentCard(props: {
  liveOrReplay: 'live' | 'replay';
  name: string;
  run: AgentRun | undefined;
  es: boolean;
  body: (run: AgentRun | undefined) => React.ReactNode;
}) {
  const { liveOrReplay, name, run, es, body } = props;
  const version = run?.agent_version || '0.1.0';
  const status = run?.status === 'success' ? 'Completado' : run ? run.status : 'Pendiente';
  return (
    <Card className="border-brand-cyan/30">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2">
            <span className="font-mono">{name}</span>
            <span className="font-mono text-xs text-fg-muted">v{version}</span>
            <Badge className="bg-brand-cyan text-fg-inverted">
              {liveOrReplay === 'live' ? 'LIVE' : 'REPLAY'}
            </Badge>
          </span>
          <Badge
            className={cn(
              run?.status === 'success'
                ? 'bg-status-resolved-bg text-status-resolved-fg'
                : 'bg-surface-subtle text-fg-muted',
            )}
          >
            {run ? (es ? 'Completado' : 'Done') : es ? 'Ejecutando…' : 'Running…'}
            {run && status !== 'Completado' ? ` (${status})` : ''}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        {run?.tool_calls && run.tool_calls.length > 0 ? (
          <div>
            <p className="text-2xs uppercase tracking-wide text-fg-muted">
              {es ? 'Logs de ejecución' : 'Execution logs'}
            </p>
            <pre className="mt-1 max-h-36 overflow-auto rounded-sbs border border-border-subtle bg-surface-subtle px-2 py-1 font-mono text-2xs leading-relaxed">
              {formatTraceLog(run.tool_calls).join('\n')}
            </pre>
          </div>
        ) : null}
        <div>
          <p className="text-2xs uppercase tracking-wide text-fg-muted">
            {es ? 'Salida' : 'Output'}
          </p>
          <div className="mt-1">{body(run)}</div>
        </div>
      </CardBody>
    </Card>
  );
}

function formatTraceLog(calls: ToolCall[]): string[] {
  if (calls.length === 0) return [];
  const baseMs = calls[0].started_at ? new Date(calls[0].started_at).getTime() : 0;
  const out: string[] = [];
  for (const c of calls) {
    const t0 = c.started_at ? new Date(c.started_at).getTime() : baseMs;
    const t1 = c.ended_at ? new Date(c.ended_at).getTime() : t0 + 100;
    const dt0 = Math.max(0, t0 - baseMs);
    const dt1 = Math.max(0, t1 - baseMs);
    const stamp = (ms: number) => {
      const s = Math.floor(ms / 1000)
        .toString()
        .padStart(2, '0');
      const r = (ms % 1000).toString().padStart(3, '0');
      return `00:${s}.${r}`;
    };
    out.push(`[${stamp(dt0)}] Llamando ${c.tool_name}…`);
    const summary = c.output ? summariseOutput(c.tool_name || '', c.output) : '';
    out.push(`[${stamp(dt1)}] ${c.tool_name} completado${summary ? ': ' + summary : ''}`);
  }
  return out;
}

function summariseOutput(tool: string, out: Record<string, unknown>): string {
  if (tool === 'bert_classifier') {
    return `classification=${out.classification ?? '?'} confidence=${out.confidence ?? '?'}`;
  }
  if (tool === 'rank_features') {
    const top = (out.top_features as Array<{ name: string; contribution: number }>)?.[0];
    if (top) return `top_feature=${top.name} weight=${top.contribution >= 0 ? '+' : ''}${top.contribution}`;
  }
  if (tool === 'anomaly_detector') {
    return `composite_score=${out.composite_score ?? '?'}`;
  }
  if (tool === 'search_similar_complaints') {
    const items = (out.items as unknown[]) || [];
    return `matches=${items.length}`;
  }
  if (tool === 'draft_narrative') {
    const text = (out.text as string) || '';
    return `text_chars=${text.length}`;
  }
  if (tool === 'compose_executive_summary') {
    const kp = (out.key_points as string[]) || [];
    return `key_points=${kp.length}`;
  }
  return '';
}

function ReplayAgentCard(props: {
  name: string;
  versionLabel: string;
  es: boolean;
  outputTitle: string;
  output: React.ReactNode;
  toolCalls: string[];
}) {
  const { name, versionLabel, es, outputTitle, output, toolCalls } = props;
  return (
    <Card className="border-fg-muted/30">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2">
            <span className="font-mono">{name}</span>
            <span className="font-mono text-xs text-fg-muted">v{versionLabel}</span>
            <Badge className="bg-fg-muted/20 text-fg">REPLAY</Badge>
          </span>
          <Badge className="bg-surface-subtle text-fg-muted">
            {es ? 'Modo replay (datos pre-generados)' : 'Replay mode (pre-generated data)'}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        <div>
          <p className="text-2xs uppercase tracking-wide text-fg-muted">
            {es ? 'Logs de ejecución' : 'Execution logs'}
          </p>
          <pre className="mt-1 max-h-32 overflow-auto rounded-sbs border border-border-subtle bg-surface-subtle px-2 py-1 font-mono text-2xs">
            {toolCalls.join('\n')}
          </pre>
        </div>
        <div>
          <p className="text-2xs uppercase tracking-wide text-fg-muted">{outputTitle}</p>
          <div className="mt-1">{output}</div>
        </div>
      </CardBody>
    </Card>
  );
}

function TriageBody(props: {
  run?: AgentRun;
  fallback: FindingPayload;
  es: boolean;
}) {
  const clf =
    (props.run?.final_output as { classification?: { label?: string; confidence?: number } })?.classification ||
    props.fallback.classification ||
    {};
  return (
    <div className="space-y-1 text-sm">
      <p>
        <span className="font-semibold">Clasificación:</span>{' '}
        <span className="font-mono">{clf.label || '—'}</span>
      </p>
      <p>
        <span className="font-semibold">Confianza:</span>{' '}
        <span className="font-mono">{(clf.confidence ?? 0).toFixed(2)}</span>
      </p>
    </div>
  );
}

function InvestigationBody(props: {
  run?: AgentRun;
  fallback: FindingPayload;
  es: boolean;
}) {
  const out = (props.run?.final_output as {
    feature_attribution?: Array<{ name: string; contribution: number }>;
    anomaly?: { composite_score?: number; threshold?: number };
  }) || {};
  const features =
    out.feature_attribution ||
    (props.fallback.features?.feature_contributions || []).map((f) => ({
      name: f.feature_name,
      contribution: f.contribution,
    }));
  const anomaly = out.anomaly || props.fallback.anomaly || {};
  return (
    <div className="space-y-2 text-sm">
      <div>
        <p className="text-2xs uppercase tracking-wide text-fg-muted">
          {props.es ? 'Top features' : 'Top features'}
        </p>
        <ul className="font-mono text-xs">
          {features.slice(0, 4).map((f) => (
            <li key={f.name}>
              {f.name}{' '}
              <span
                className={
                  f.contribution >= 0 ? 'text-status-escalated-fg' : 'text-fg-muted'
                }
              >
                ({f.contribution >= 0 ? '+' : ''}
                {f.contribution.toFixed(2)})
              </span>
            </li>
          ))}
        </ul>
      </div>
      <p>
        <span className="font-semibold">Anomalía compuesta:</span>{' '}
        <span className="font-mono">{anomaly.composite_score?.toFixed(2) ?? '—'}</span>{' '}
        <span className="text-fg-muted">
          (umbral {anomaly.threshold?.toFixed(2) ?? '0.70'})
        </span>
      </p>
    </div>
  );
}

function SynthesisBody(props: {
  run?: AgentRun;
  fallback: FindingPayload;
  es: boolean;
}) {
  const out = (props.run?.final_output as { executive_summary?: { text?: string; key_points?: string[] } }) || {};
  const summary = out.executive_summary || props.fallback.executive_summary || {};
  const draft = props.fallback.agent_drafted_narrative || '';
  return (
    <div className="space-y-2 text-sm">
      <div>
        <p className="text-2xs uppercase tracking-wide text-fg-muted">
          {props.es ? 'Resumen ejecutivo (extracto)' : 'Executive brief (excerpt)'}
        </p>
        <p className="text-sm leading-relaxed text-fg">
          {(summary.text || '').slice(0, 280) || '—'}
        </p>
      </div>
      {summary.key_points ? (
        <ul className="ml-4 list-disc text-xs leading-relaxed">
          {summary.key_points.slice(0, 4).map((kp, i) => (
            <li key={i}>{kp}</li>
          ))}
        </ul>
      ) : null}
      {draft ? (
        <div>
          <p className="text-2xs uppercase tracking-wide text-fg-muted">
            {props.es ? 'Borrador del agente (primeras 200 letras)' : 'Agent draft (first 200 chars)'}
          </p>
          <p className="font-mono text-xs leading-relaxed text-fg">
            {draft.slice(0, 200)}…
          </p>
        </div>
      ) : null}
    </div>
  );
}
