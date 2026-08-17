// SPDX-License-Identifier: Apache-2.0
// Lists recent complaints split into "in flight" and "completed".
// A complaint is "in flight" if any of the 4 pipeline stages
// (live-ingestion-orchestrator, triage, investigation, synthesis) is
// missing or not in a terminal status; otherwise it's "completed".
//
// Refreshes every 2.5 s so the live ticker on /app/ingestion has a
// visible mirror here.
/* eslint-disable i18next/no-literal-string */

'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, ChevronRight, Loader2, Minus } from 'lucide-react';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

interface RecentItem {
  complaint_id: string;
  institution_id: string;
  received_at: string;
  motivo_code: string;
  product_category: string;
  narrative_preview: string;
  agents: Record<string, { status: string; started_at: string; ended_at?: string }>;
  anomaly_score?: number;
  classification?: { label: string; confidence: number };
}

interface Props {
  locale: Locale;
}

const PIPELINE_AGENTS: Array<{ name: string; label_es: string; label_en: string }> = [
  { name: 'live-ingestion-orchestrator', label_es: 'Ingesta', label_en: 'Ingest' },
  { name: 'triage', label_es: 'Triage', label_en: 'Triage' },
  { name: 'investigation', label_es: 'Investigación', label_en: 'Investigation' },
  { name: 'synthesis', label_es: 'Síntesis', label_en: 'Synthesis' },
];

const TERMINAL_GRACE_MS = 20_000;

// Triage can route a complaint info-only (score below the 0.70 threshold):
// triage finishes and the downstream stages are never scheduled. The journey
// payload carries no route_to field, so this is inferred presentationally:
// triage done + investigation/synthesis absent + a grace window elapsed.
function isInfoOnlyTerminal(item: RecentItem): boolean {
  const triage = item.agents['triage'];
  if (!triage || (triage.status !== 'success' && triage.status !== 'partial')) return false;
  if (item.agents['investigation'] || item.agents['synthesis']) return false;
  const ts = Date.parse(triage.ended_at ?? triage.started_at);
  return Number.isFinite(ts) && Date.now() - ts > TERMINAL_GRACE_MS;
}

function isInFlight(item: RecentItem): boolean {
  if (isInfoOnlyTerminal(item)) return false;
  return PIPELINE_AGENTS.some(({ name }) => {
    const a = item.agents[name];
    if (!a) return true;
    return a.status !== 'success' && a.status !== 'partial';
  });
}

export function ProcessingListClient({ locale }: Props) {
  const es = locale === 'es-PE';
  const [items, setItems] = useState<RecentItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const pull = async () => {
      try {
        const r = await fetch('/app/api/journey/recent?limit=40', { cache: 'no-store' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const json = (await r.json()) as { items?: RecentItem[] };
        if (!cancelled) {
          setItems(json.items || []);
          setError(null);
        }
      } catch (exc) {
        if (!cancelled) setError(String(exc));
      }
    };
    pull();
    const id = window.setInterval(pull, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const { inflight, completed } = useMemo(() => {
    const inflight: RecentItem[] = [];
    const completed: RecentItem[] = [];
    for (const it of items) {
      if (isInFlight(it)) inflight.push(it);
      else completed.push(it);
    }
    return { inflight, completed };
  }, [items]);

  return (
    <div className="space-y-4">
      {error ? <p className="text-sm text-danger">{error}</p> : null}
      <Card className="border-brand-cyan/40">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-brand-cyan" />
              {es ? `En proceso (${inflight.length})` : `In flight (${inflight.length})`}
            </span>
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-2">
          {inflight.length === 0 ? (
            <p className="text-sm text-fg-muted">
              {es ? 'No hay reclamos en curso ahora mismo.' : 'No complaints in flight right now.'}
            </p>
          ) : null}
          {inflight.map((c) => (
            <Row key={c.complaint_id} item={c} locale={locale} />
          ))}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2 className="h-4 w-4 text-status-resolved-fg" />
            {es ? `Completados (${completed.length})` : `Completed (${completed.length})`}
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-2">
          {completed.length === 0 ? (
            <p className="text-sm text-fg-muted">
              {es ? 'Ningún reclamo completado todavía.' : 'No complaints completed yet.'}
            </p>
          ) : null}
          {completed.map((c) => (
            <Row key={c.complaint_id} item={c} locale={locale} />
          ))}
        </CardBody>
      </Card>
    </div>
  );
}

function Row({ item, locale }: { item: RecentItem; locale: Locale }) {
  const es = locale === 'es-PE';
  const infoOnly = isInfoOnlyTerminal(item);
  return (
    <Link
      href={`/processing/${item.complaint_id}`}
      className="block rounded-sbs border border-border-subtle bg-surface px-3 py-2 transition-colors hover:border-brand-cyan/40 hover:bg-surface-subtle"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-medium text-fg">{item.complaint_id}</span>
            <span className="rounded-sm bg-surface-subtle px-1.5 py-0.5 font-mono text-2xs text-fg-muted">
              {item.institution_id}
            </span>
            {item.classification ? (
              <span className="rounded-sm bg-brand-cyan/15 px-1.5 py-0.5 font-mono text-2xs text-brand-navy">
                {item.classification.label} · {item.classification.confidence?.toFixed(2)}
              </span>
            ) : null}
            {typeof item.anomaly_score === 'number' && item.anomaly_score >= 0.7 ? (
              <span className="rounded-sm bg-brand-gold/20 px-1.5 py-0.5 font-mono text-2xs text-brand-navy">
                ⚠ {item.anomaly_score.toFixed(2)}
              </span>
            ) : null}
            {infoOnly ? (
              <span className="rounded-sm bg-surface-subtle px-1.5 py-0.5 font-mono text-2xs text-fg-muted">
                {es ? 'solo informativo' : 'info-only'}
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 font-mono text-2xs text-fg-muted">
            {item.motivo_code} · {item.product_category} ·{' '}
            {new Date(item.received_at).toLocaleTimeString()}
          </p>
          <p className="mt-1 truncate text-xs text-fg/80">{item.narrative_preview}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            {PIPELINE_AGENTS.map(({ name, label_es, label_en }) => {
              const a = item.agents[name];
              const done = a?.status === 'success' || a?.status === 'partial';
              const skipped = infoOnly && (name === 'investigation' || name === 'synthesis');
              return (
                <span
                  key={name}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-sbs border px-1.5 py-0.5 font-mono text-2xs',
                    done
                      ? 'border-status-resolved-border bg-status-resolved-bg/40 text-status-resolved-fg'
                      : 'border-border text-fg-muted',
                  )}
                >
                  {done ? (
                    <CheckCircle2 className="h-3 w-3" />
                  ) : skipped ? (
                    <Minus className="h-3 w-3" />
                  ) : (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  )}
                  {es ? label_es : label_en}
                </span>
              );
            })}
          </div>
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-fg-muted" />
      </div>
    </Link>
  );
}
