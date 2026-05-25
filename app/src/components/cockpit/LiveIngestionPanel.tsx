// LiveIngestionPanel — wired to the P11A demo ingestion endpoint.
//
// Clicking Submit calls /app/api/ingest, which proxies to
// /v1/internal/demo/simulate-submission. The backend deterministically
// redacts PII, runs data-quality checks, persists a canonical
// complaint, writes one agent_runs row, records five audit events,
// and publishes one complaint.received SSE delta. The response
// payload carries the timeline, masked-before / redacted-after diff,
// detected entities, data-quality report, and persistence handles —
// all of which the panel renders below.
//
// PII safety: the BEFORE preview is a server-side **masked** version
// of the raw narrative — full raw PII never reaches the browser.

'use client';

import { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Hash,
  Info,
  Lightbulb,
  Lock,
  Play,
  Send,
  ShieldCheck,
} from 'lucide-react';

import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';

interface EntityLabels {
  pii_name: string;
  pii_id: string;
  pii_phone: string;
  pii_email: string;
  pii_account: string;
  pii_address: string;
}

interface Labels {
  title: string;
  subtitle: string;
  sandbox_badge: string;
  nrt_label: string;
  submit_button: string;
  submitting: string;
  submit_again_button: string;
  error_title: string;
  error_body: string;
  error_detail_label: string;
  evidence_label: string;
  idle_hint: string;
  timeline_title: string;
  diff_title: string;
  diff_tag_before: string;
  diff_tag_after: string;
  redaction_entities_title: string;
  redaction_entity_kinds: EntityLabels;
  redaction_no_entities: string;
  redaction_policy_footer: string;
  dq_title: string;
  dq_errors_label: string;
  dq_warnings_label: string;
  dq_suggested_label: string;
  dq_empty: string;
  dq_policy_footer: string;
  ids_title: string;
  complaint_id_label: string;
  raw_id_label: string;
  agent_run_id_label: string;
  event_id_label: string;
  event_id_pending: string;
  events: {
    received: string;
    institution_authenticated_simulated: string;
    schema_validated: string;
    pii_redacted: string;
    canonical_complaint_persisted: string;
    data_quality_checks_completed: string;
    finding_triage_event_emitted: string;
  };
}

interface LiveIngestionPanelProps {
  labels: Labels;
  csrfToken: string;
}

interface RedactionEntity {
  kind: keyof EntityLabels;
  rule_id: string;
  span: [number, number];
  replacement: string;
  confidence: number;
}

interface RedactionDiff {
  before_masked: string;
  after_redacted: string;
  policy_version: string;
  entities: RedactionEntity[];
  entity_count_by_kind: Partial<Record<keyof EntityLabels, number>>;
}

interface DqIssue {
  rule_id: string;
  field: string;
  message: string;
}

interface DqEnrichment {
  rule_id: string;
  field: string;
  suggested_value: unknown;
  evidence: string;
}

interface DataQualityEnvelope {
  errors: DqIssue[];
  warnings: DqIssue[];
  suggested_enrichments: DqEnrichment[];
  extracted_fields: Record<string, unknown>;
  policy_version: string;
}

interface TimelineEvent {
  event: keyof Labels['events'];
  at: string;
  detail: string | null;
}

interface IngestionResponse {
  complaint_id: string;
  raw_complaint_id: string;
  institution_id: string;
  institution_name: string | null;
  agent_run_id: string | null;
  event_id: number | null;
  timeline: TimelineEvent[];
  redaction_diff: RedactionDiff;
  data_quality: DataQualityEnvelope;
}

// Fixed realistic demo payload. The narrative carries the canonical
// "Carlos Rodríguez Mendoza" + DNI + phone + email + card-number
// patterns the redaction engine is tested against. Amount mentions
// like "S/ 700" exercise the data-quality amount-extraction path.
const DEMO_PAYLOAD = {
  institution_id: 'SBS-001234',
  institution_name: 'BANCO_DEMO_001',
  institution_complaint_id: 'BCO-DEMO-IN-0001',
  client_submission_id: 'live-demo-001',
  received_at: '2026-05-24T10:15:00-05:00',
  channel_in: 'APP_MOVIL',
  channel_operation: 'APP_MOVIL',
  product: 'TARJETA_CREDITO',
  motive: 'COBRO_INDEBIDO',
  narrative:
    'El cliente Carlos Rodríguez Mendoza (DNI 12345678) reporta un cargo no reconocido por S/ 700 en la tarjeta 4556 1234 5678 9999. Indica que recibió notificaciones por su billetera digital y solicita que lo contactemos al +51 987 654 321 o al correo carlos.rodriguez@example.com.',
  response_detail: null,
  status: 'pendiente',
  severity: 'HIGH',
  demo_scenario: 'live-ingestion-panel-default',
} as const;

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}

function applyTemplate(template: string, values: Record<string, string>): string {
  return Object.entries(values).reduce(
    (acc, [key, value]) => acc.replace(`{${key}}`, value),
    template,
  );
}

export function LiveIngestionPanel({ labels, csrfToken }: LiveIngestionPanelProps) {
  const [state, setState] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle');
  const [response, setResponse] = useState<IngestionResponse | null>(null);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  const submit = async () => {
    setState('submitting');
    setErrorDetail(null);
    try {
      const res = await fetch('/app/api/ingest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-SBS-CSRF': csrfToken,
        },
        body: JSON.stringify(DEMO_PAYLOAD),
        credentials: 'same-origin',
      });
      if (!res.ok) {
        setState('error');
        setErrorDetail(`HTTP ${res.status}`);
        return;
      }
      const json = (await res.json()) as IngestionResponse;
      setResponse(json);
      setState('success');
    } catch (err) {
      setState('error');
      setErrorDetail(err instanceof Error ? err.message : 'unknown');
    }
  };

  const reset = () => {
    setState('idle');
    setResponse(null);
    setErrorDetail(null);
  };

  return (
    <section
      aria-label={labels.title}
      className="overflow-hidden rounded-sbs border border-border bg-surface shadow-sm"
      style={{ borderLeft: '3px solid var(--color-brand-navy)' }}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex min-w-0 flex-col">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-fg">{labels.title}</h2>
            <Badge
              variant="role"
              className="border-brand-gold/40 bg-brand-gold/10 text-brand-navy"
            >
              {labels.sandbox_badge}
            </Badge>
          </div>
          <p className="text-xs text-fg-muted">{labels.subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-fg-subtle">
            <Lock className="h-3 w-3" aria-hidden="true" />
            {labels.nrt_label}
          </span>
          {state === 'success' ? (
            <Button type="button" variant="outline" size="sm" onClick={reset}>
              <Send className="h-3.5 w-3.5" aria-hidden="true" />
              {labels.submit_again_button}
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={submit}
              disabled={state === 'submitting'}
            >
              <Send className="h-3.5 w-3.5" aria-hidden="true" />
              {state === 'submitting' ? labels.submitting : labels.submit_button}
            </Button>
          )}
        </div>
      </header>

      {state === 'idle' || state === 'submitting' ? (
        <div className="flex items-center gap-2 border-b border-border bg-surface-subtle px-4 py-2 text-xs text-fg-muted">
          <Info className="h-3.5 w-3.5 text-brand-gold" aria-hidden="true" />
          <span>{labels.idle_hint}</span>
        </div>
      ) : null}

      {state === 'error' ? (
        <div className="border-b border-severity-high-border bg-severity-high-bg/40 px-4 py-3 text-xs text-severity-high-fg">
          <div className="flex items-center gap-2 font-semibold">
            <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
            {labels.error_title}
          </div>
          <p className="mt-1">{labels.error_body}</p>
          {errorDetail ? (
            <p className="mt-1 font-mono text-2xs text-fg-muted">
              {labels.error_detail_label}
              {': '}
              {errorDetail}
            </p>
          ) : null}
        </div>
      ) : null}

      {state === 'success' && response ? (
        <div className="grid gap-4 p-4 md:grid-cols-[1.2fr_1.4fr]">
          <div>
            <h3 className="mb-2 flex items-center gap-2 font-mono text-2xs uppercase tracking-wider text-fg-muted">
              <Play className="h-3 w-3" aria-hidden="true" />
              {labels.timeline_title}
            </h3>
            <ol className="relative space-y-2 border-l border-border-strong pl-4">
              {response.timeline.map((ev, idx) => (
                <li key={`${ev.event}-${idx}`} className="flex items-start gap-2 text-xs">
                  <span
                    className="-ml-[1.4rem] mt-0.5 inline-flex h-3 w-3 items-center justify-center rounded-full bg-surface"
                    aria-hidden="true"
                  >
                    <CheckCircle2 className="h-3 w-3 text-severity-low-fg" />
                  </span>
                  <span className="font-mono text-2xs tabular text-fg-subtle">
                    {formatTime(ev.at)}
                  </span>
                  <span className="flex-1">
                    <span className="block text-fg">
                      {labels.events[ev.event] ?? ev.event}
                    </span>
                    {ev.detail ? (
                      <span className="block font-mono text-2xs text-fg-muted">{ev.detail}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ol>
            <IdsBlock labels={labels} response={response} />
          </div>

          <div className="space-y-4">
            <RedactionBlock labels={labels} diff={response.redaction_diff} />
            <DataQualityBlock labels={labels} report={response.data_quality} />
          </div>
        </div>
      ) : null}
    </section>
  );
}

function RedactionBlock({ labels, diff }: { labels: Labels; diff: RedactionDiff }) {
  const totalEntities = diff.entities.length;
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-2 font-mono text-2xs uppercase tracking-wider text-fg-muted">
        <ShieldCheck className="h-3 w-3" aria-hidden="true" />
        {labels.diff_title}
      </h3>
      <div className="space-y-2">
        <div className="rounded-sbs border border-severity-high-border bg-severity-high-bg/40 p-2 text-xs">
          <span className="block font-mono text-2xs font-semibold uppercase tracking-wider text-severity-high-fg">
            {labels.diff_tag_before}
          </span>
          <span className="block font-mono text-xs leading-snug text-fg">
            {diff.before_masked}
          </span>
        </div>
        <div className="rounded-sbs border border-severity-low-border bg-severity-low-bg/40 p-2 text-xs">
          <span className="block font-mono text-2xs font-semibold uppercase tracking-wider text-severity-low-fg">
            {labels.diff_tag_after}
          </span>
          <span className="block font-mono text-xs leading-snug text-fg">
            {diff.after_redacted}
          </span>
        </div>
      </div>

      <div className="mt-3">
        <span className="block font-mono text-2xs uppercase tracking-wider text-fg-muted">
          {labels.redaction_entities_title}
        </span>
        {totalEntities === 0 ? (
          <p className="mt-1 text-xs text-fg-muted">{labels.redaction_no_entities}</p>
        ) : (
          <ul className="mt-1 flex flex-wrap gap-1">
            {diff.entities.map((ent, idx) => {
              const kindLabel = labels.redaction_entity_kinds[ent.kind] ?? ent.kind;
              return (
                <li
                  key={`${ent.kind}-${idx}`}
                  className="inline-flex items-center gap-1 rounded-sbs border border-border bg-surface-subtle px-1.5 py-0.5 font-mono text-2xs text-fg"
                >
                  <span className="font-semibold">{kindLabel}</span>
                  <span className="text-fg-muted">·</span>
                  <span>{ent.replacement}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <p className="mt-2 font-mono text-2xs text-fg-muted">
        {applyTemplate(labels.redaction_policy_footer, {
          policy: diff.policy_version,
          count: String(totalEntities),
        })}
      </p>
    </div>
  );
}

function DataQualityBlock({
  labels,
  report,
}: {
  labels: Labels;
  report: DataQualityEnvelope;
}) {
  const hasAny =
    report.errors.length + report.warnings.length + report.suggested_enrichments.length > 0;
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-2 font-mono text-2xs uppercase tracking-wider text-fg-muted">
        <Lightbulb className="h-3 w-3" aria-hidden="true" />
        {labels.dq_title}
      </h3>
      {!hasAny ? (
        <p className="text-xs text-fg-muted">{labels.dq_empty}</p>
      ) : (
        <div className="space-y-2">
          {report.errors.length > 0 ? (
            <DqIssueList title={labels.dq_errors_label} items={report.errors} severity="high" />
          ) : null}
          {report.warnings.length > 0 ? (
            <DqIssueList
              title={labels.dq_warnings_label}
              items={report.warnings}
              severity="medium"
            />
          ) : null}
          {report.suggested_enrichments.length > 0 ? (
            <DqEnrichmentList
              title={labels.dq_suggested_label}
              items={report.suggested_enrichments}
              evidenceLabel={labels.evidence_label}
            />
          ) : null}
        </div>
      )}
      <p className="mt-2 font-mono text-2xs text-fg-muted">
        {applyTemplate(labels.dq_policy_footer, { policy: report.policy_version })}
      </p>
    </div>
  );
}

function DqIssueList({
  title,
  items,
  severity,
}: {
  title: string;
  items: DqIssue[];
  severity: 'high' | 'medium';
}) {
  const tone =
    severity === 'high'
      ? 'border-severity-high-border bg-severity-high-bg/30 text-severity-high-fg'
      : 'border-severity-medium-border bg-severity-medium-bg/30 text-severity-medium-fg';
  return (
    <div className={`rounded-sbs border p-2 text-xs ${tone}`}>
      <span className="block font-mono text-2xs font-semibold uppercase tracking-wider">
        {title}
      </span>
      <ul className="mt-1 space-y-1">
        {items.map((it, idx) => (
          <li key={`${it.rule_id}-${idx}`} className="flex flex-col">
            <span className="font-mono text-2xs text-fg-muted">
              {it.rule_id} · {it.field}
            </span>
            <span className="text-fg">{it.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DqEnrichmentList({
  title,
  items,
  evidenceLabel,
}: {
  title: string;
  items: DqEnrichment[];
  evidenceLabel: string;
}) {
  return (
    <div className="rounded-sbs border border-border bg-surface-subtle p-2 text-xs text-fg">
      <span className="block font-mono text-2xs font-semibold uppercase tracking-wider text-fg-muted">
        {title}
      </span>
      <ul className="mt-1 space-y-1">
        {items.map((it, idx) => (
          <li key={`${it.rule_id}-${idx}`} className="flex flex-col">
            <span className="font-mono text-2xs text-fg-muted">
              {it.rule_id} · {it.field}
            </span>
            <span className="text-fg">
              → <span className="font-mono">{String(it.suggested_value)}</span>
            </span>
            <span className="font-mono text-2xs text-fg-muted">
              {evidenceLabel}
              {': '}
              {it.evidence}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function IdsBlock({ labels, response }: { labels: Labels; response: IngestionResponse }) {
  return (
    <div className="mt-3 rounded-sbs border border-border bg-surface-subtle p-2 text-xs">
      <span className="mb-1 flex items-center gap-2 font-mono text-2xs uppercase tracking-wider text-fg-muted">
        <Hash className="h-3 w-3" aria-hidden="true" />
        {labels.ids_title}
      </span>
      <dl className="space-y-1">
        <IdRow label={labels.complaint_id_label} value={response.complaint_id} />
        <IdRow label={labels.raw_id_label} value={response.raw_complaint_id} />
        {response.agent_run_id ? (
          <IdRow label={labels.agent_run_id_label} value={response.agent_run_id} />
        ) : null}
        <IdRow
          label={labels.event_id_label}
          value={
            response.event_id !== null && response.event_id !== undefined
              ? String(response.event_id)
              : labels.event_id_pending
          }
        />
      </dl>
    </div>
  );
}

function IdRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="min-w-0 shrink-0 font-mono text-2xs uppercase tracking-wider text-fg-muted">
        {label}
      </dt>
      <dd className="break-all font-mono text-2xs text-fg">{value}</dd>
    </div>
  );
}
