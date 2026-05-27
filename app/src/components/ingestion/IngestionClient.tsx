// Live ingestion theatre. Client drives a configurable-interval loop
// that POSTs successive sample rows through /app/api/journey/submit
// (which runs the real mTLS + OAuth + HMAC chain). A second panel
// polls /app/api/journey/recent every 2 s so the operator sees SBS
// receiving traffic with agent state.
//
// i18next literal-string disabled — most strings here are operator-
// facing technical labels (complaint_id, agent names, timing).
/* eslint-disable i18next/no-literal-string */

'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CheckCircle2,
  ChevronRight,
  Pause,
  Play,
  Loader2,
  Radio,
  RefreshCcw,
  XCircle,
} from 'lucide-react';

import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

interface EmailRow {
  COD_REC?: string;
  NCL_CLI?: string;
  TID_CLI?: string;
  NRO_CLI?: string;
  COD_CLI?: string;
  FEC_ING?: string;
  CNL_ING?: string;
  CNL_OPE?: string;
  UBI_REC?: string;
  PRD_SBS?: string;
  MOT_SBS?: string;
  SUB_SBS?: string;
  DET_REC?: string;
  __institution: string;
}

interface SentEntry {
  rowIndex: number;
  customer: string;
  cod_rec: string;
  motive: string;
  status: 'sending' | 'ok' | 'fail';
  complaintId?: string;
  error?: string;
  startedAt: number;
  endedAt?: number;
}

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
  emails: Array<Record<string, unknown>>;
  csrfToken: string;
}

const PIPELINE_AGENTS = ['live-ingestion-orchestrator', 'triage', 'investigation', 'synthesis'];

export function IngestionClient({ locale, emails, csrfToken }: Props) {
  const rows = emails as unknown as EmailRow[];
  const es = locale === 'es-PE';

  // Ticker control
  const [running, setRunning] = useState(false);
  const [interval, setInterval] = useState(4);
  const [cursor, setCursor] = useState(0);
  const [sent, setSent] = useState<SentEntry[]>([]);
  const cursorRef = useRef(cursor);
  cursorRef.current = cursor;
  const sentRef = useRef(sent);
  sentRef.current = sent;
  const runningRef = useRef(running);
  runningRef.current = running;

  const submit = useCallback(
    async (idx: number) => {
      const row = rows[idx];
      const entry: SentEntry = {
        rowIndex: idx,
        customer: String(row.NCL_CLI || '—'),
        cod_rec: String(row.COD_REC || `idx-${idx}`),
        motive: String(row.MOT_SBS || '—'),
        status: 'sending',
        startedAt: Date.now(),
      };
      setSent((s) => [entry, ...s].slice(0, 30));
      try {
        const body = {
          institution_complaint_id: row.COD_REC,
          tid_cli: row.TID_CLI,
          nro_cli: row.NRO_CLI,
          ncl_cli: row.NCL_CLI,
          cod_cli: row.COD_CLI,
          received_at: row.FEC_ING,
          channel_in: row.CNL_ING,
          channel_operation: row.CNL_OPE,
          ubigeo: row.UBI_REC,
          product: row.PRD_SBS,
          motive: row.MOT_SBS,
          submotive: row.SUB_SBS,
          narrative: row.DET_REC,
          severity: 'MEDIUM',
        };
        const r = await fetch('/app/api/journey/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'x-sbs-csrf': csrfToken },
          body: JSON.stringify(body),
        });
        const json = (await r.json()) as { ok?: boolean; error?: string; trace?: { complaint_id?: string } };
        const update: Partial<SentEntry> =
          json.ok && json.trace?.complaint_id
            ? { status: 'ok', complaintId: json.trace.complaint_id, endedAt: Date.now() }
            : { status: 'fail', error: json.error || 'submit failed', endedAt: Date.now() };
        setSent((s) =>
          s.map((e) => (e.rowIndex === idx && e.startedAt === entry.startedAt ? { ...e, ...update } : e)),
        );
      } catch (exc) {
        setSent((s) =>
          s.map((e) =>
            e.rowIndex === idx && e.startedAt === entry.startedAt
              ? { ...e, status: 'fail', error: String(exc), endedAt: Date.now() }
              : e,
          ),
        );
      }
    },
    [rows, csrfToken],
  );

  // Ticker loop. Uses a ref-backed running flag + setTimeout so toggling
  // mid-flight stops cleanly after the in-flight request resolves.
  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled || !runningRef.current) return;
      const idx = cursorRef.current % rows.length;
      setCursor((c) => c + 1);
      await submit(idx);
      if (cancelled || !runningRef.current) return;
      setTimeout(tick, interval * 1000);
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [running, interval, rows.length, submit]);

  // Live "recent in SBS" panel — polls /app/api/journey/recent.
  const [recent, setRecent] = useState<RecentItem[]>([]);
  const [recentError, setRecentError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    const pull = async () => {
      try {
        const r = await fetch('/app/api/journey/recent?limit=20', { cache: 'no-store' });
        if (r.ok) {
          const json = (await r.json()) as { items?: RecentItem[] };
          if (!cancelled) {
            setRecent(json.items || []);
            setRecentError(null);
          }
        } else if (!cancelled) {
          setRecentError(`HTTP ${r.status}`);
        }
      } catch (exc) {
        if (!cancelled) setRecentError(String(exc));
      }
    };
    pull();
    const id = window.setInterval(pull, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
      <Card className="border-brand-cyan/40">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <Radio className={cn('h-4 w-4', running && 'animate-pulse text-status-resolved-fg')} />
              {es ? 'Controlador de ingesta' : 'Ingestion controller'}
            </span>
          </CardTitle>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setRunning((r) => !r)}
              className={cn(
                'inline-flex h-9 items-center gap-1.5 rounded-sbs px-3 text-sm font-medium',
                running
                  ? 'bg-severity-medium-bg text-severity-medium-fg'
                  : 'bg-brand-navy text-fg-inverted hover:bg-brand-navy/90',
              )}
            >
              {running ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
              {running ? (es ? 'Pausar' : 'Pause') : es ? 'Iniciar envío' : 'Start feeding'}
            </button>
            <button
              type="button"
              onClick={() => {
                setCursor(0);
                setSent([]);
              }}
              className="inline-flex h-9 items-center gap-1.5 rounded-sbs border border-border-strong bg-surface px-3 text-sm text-fg hover:bg-surface-subtle"
            >
              <RefreshCcw className="h-3.5 w-3.5" />
              {es ? 'Reiniciar' : 'Reset'}
            </button>
          </div>

          <div>
            <label htmlFor="interval" className="block text-xs font-medium text-fg">
              {es ? `Intervalo: ${interval}s` : `Interval: ${interval}s`}
            </label>
            <input
              id="interval"
              type="range"
              min={2}
              max={15}
              step={1}
              value={interval}
              onChange={(e) => setInterval(Number.parseInt(e.target.value, 10))}
              className="mt-1 w-full"
            />
            <p className="mt-1 text-2xs text-fg-muted">
              {es
                ? 'Cada N segundos se firma + envía la siguiente fila del muestreo.'
                : 'Every N seconds, the next sample row is signed + submitted.'}
            </p>
          </div>

          <div className="rounded-sbs border border-border-subtle bg-surface-subtle px-3 py-2 text-xs">
            <p className="text-fg-muted">
              {es ? 'Posición en muestreo' : 'Sample cursor'}:{' '}
              <span className="font-mono text-fg">
                {cursor}/{rows.length}
              </span>
            </p>
            <p className="mt-0.5 text-fg-muted">
              {es ? 'Enviados en esta sesión' : 'Sent this session'}:{' '}
              <span className="font-mono text-fg">{sent.length}</span>
            </p>
          </div>

          <div>
            <p className="mb-1 text-2xs uppercase tracking-wide text-fg-muted">
              {es ? 'Últimos envíos' : 'Last sent'}
            </p>
            <ul className="max-h-72 space-y-1 overflow-y-auto text-xs">
              {sent.length === 0 ? (
                <li className="text-fg-muted">
                  {es ? 'Aún sin envíos. Pulsa Iniciar.' : 'Nothing sent yet. Press Start.'}
                </li>
              ) : null}
              {sent.map((s) => (
                <li
                  key={`${s.rowIndex}-${s.startedAt}`}
                  className={cn(
                    'rounded-sbs border px-2 py-1.5',
                    s.status === 'ok'
                      ? 'border-status-resolved-border bg-status-resolved-bg/40'
                      : s.status === 'fail'
                        ? 'border-danger bg-severity-high-bg'
                        : 'border-border-subtle bg-surface',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium text-fg">{s.customer}</span>
                    {s.status === 'sending' ? (
                      <Loader2 className="h-3 w-3 shrink-0 animate-spin text-fg-muted" />
                    ) : s.status === 'ok' ? (
                      <CheckCircle2 className="h-3 w-3 shrink-0 text-status-resolved-fg" />
                    ) : (
                      <XCircle className="h-3 w-3 shrink-0 text-danger" />
                    )}
                  </div>
                  <p className="font-mono text-2xs text-fg-muted">
                    {s.cod_rec} · {s.motive}
                  </p>
                  {s.complaintId ? (
                    <Link
                      href={`/processing/${s.complaintId}`}
                      className="font-mono text-2xs text-brand-cyan hover:underline"
                    >
                      → {s.complaintId}
                    </Link>
                  ) : null}
                  {s.error ? (
                    <p className="font-mono text-2xs text-danger">{s.error}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span>
              {es ? 'SBS está recibiendo · últimos 20 reclamos' : 'SBS is receiving · last 20 complaints'}
            </span>
            <span className="font-mono text-2xs text-fg-muted">
              {es ? 'refresca cada 2.5s' : 'refreshes every 2.5s'}
            </span>
          </CardTitle>
        </CardHeader>
        <CardBody>
          {recentError ? (
            <p className="text-sm text-danger">Error: {recentError}</p>
          ) : null}
          <ul className="space-y-2">
            {recent.length === 0 ? (
              <li className="text-sm text-fg-muted">
                {es ? 'Sin reclamos recibidos aún.' : 'No complaints received yet.'}
              </li>
            ) : null}
            {recent.map((r) => {
              const totalAgents = PIPELINE_AGENTS.length;
              const doneAgents = PIPELINE_AGENTS.filter(
                (n) => r.agents[n]?.status === 'success' || r.agents[n]?.status === 'partial',
              ).length;
              return (
                <li key={r.complaint_id}>
                  <Link
                    href={`/processing/${r.complaint_id}`}
                    className="block rounded-sbs border border-border-subtle bg-surface px-3 py-2 transition-colors hover:border-brand-cyan/40 hover:bg-surface-subtle"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="flex items-center gap-2 text-sm font-medium text-fg">
                          <span className="font-mono">{r.complaint_id}</span>
                          <span className="rounded-sm bg-surface-subtle px-1.5 py-0.5 font-mono text-2xs text-fg-muted">
                            {r.institution_id}
                          </span>
                          {r.classification ? (
                            <span className="rounded-sm bg-brand-cyan/15 px-1.5 py-0.5 font-mono text-2xs text-brand-navy">
                              {r.classification.label}
                            </span>
                          ) : null}
                          {typeof r.anomaly_score === 'number' && r.anomaly_score >= 0.7 ? (
                            <span className="rounded-sm bg-brand-gold/20 px-1.5 py-0.5 font-mono text-2xs text-brand-navy">
                              ⚠ {r.anomaly_score.toFixed(2)}
                            </span>
                          ) : null}
                        </p>
                        <p className="mt-0.5 font-mono text-2xs text-fg-muted">
                          {r.motivo_code} · {r.product_category} ·{' '}
                          {new Date(r.received_at).toLocaleTimeString()}
                        </p>
                        <p className="mt-1 truncate text-xs text-fg/80">{r.narrative_preview}</p>
                        <div className="mt-1 flex items-center gap-1.5">
                          {PIPELINE_AGENTS.map((name) => {
                            const a = r.agents[name];
                            const done = a?.status === 'success' || a?.status === 'partial';
                            return (
                              <span
                                key={name}
                                title={`${name}${a ? ` · ${a.status}` : ' · pending'}`}
                                className={cn(
                                  'h-1.5 w-8 rounded-full',
                                  done ? 'bg-status-resolved-fg' : 'bg-border',
                                )}
                              />
                            );
                          })}
                          <span className="font-mono text-2xs text-fg-muted">
                            {doneAgents}/{totalAgents}
                          </span>
                        </div>
                      </div>
                      <ChevronRight className="h-4 w-4 shrink-0 text-fg-muted" />
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </CardBody>
      </Card>
    </div>
  );
}
