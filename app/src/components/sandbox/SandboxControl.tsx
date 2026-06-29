// SPDX-License-Identifier: Apache-2.0
/* eslint-disable i18next/no-literal-string */
'use client';

import { Building2, CheckCircle2, ExternalLink, FileUp, Loader2, Pause, Play, RefreshCw, Send, Zap } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import { Badge, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { cn } from '@/lib/cn';

// Bank-side control surfaces. Tier-1 panel here; Tier-2 panel added alongside.
// Every action POSTs to a BFF that spawns the REAL signed sender and returns
// the REAL API response — no fake animation.

const PROFILES = [
  { id: 'banco-tier1', label: 'Banco Demo 001', institution: 'SBS-001234' },
  { id: 'coopac-tier2', label: 'Coopac Demo 002', institution: 'SBS-005678' },
] as const;
type ProfileId = (typeof PROFILES)[number]['id'];

const FREQS = [5, 10, 30] as const;

interface PoolItem {
  idx: number;
  motive?: string;
  product?: string;
  channel?: string;
  severity?: string;
  narrative?: string;
  payload: Record<string, unknown>;
}
interface SendResult {
  ok: boolean;
  http_status: number | null;
  complaint_id?: string | null;
  decision?: string | null;
  motive?: string;
  product?: string;
  severity?: string;
  error?: string;
}
interface BatchRow {
  complaint_id: string;
  motivo?: string;
}
interface BatchState {
  batch_id?: string | null;
  status?: string | null;
  http_status?: number | null;
  row_count_submitted?: number;
  row_count_accepted?: number;
  row_count_rejected?: number;
  rows?: BatchRow[];        // ordered CSV rows the batch actually carried
  rejected_rows?: number[]; // 0-indexed CSV positions the worker rejected
  error?: string;
}

const BATCH_ROW_CAP = 50;

function batchTone(s?: string | null): string {
  const v = (s ?? '').toLowerCase();
  if (v === 'complete') return 'border-green-600/40 bg-green-50 text-green-700';
  if (v === 'failed') return 'border-red-600/40 bg-red-50 text-red-700';
  if (v === 'processing') return 'border-brand-cyan/40 bg-brand-cyan/10 text-brand-navy';
  return 'border-amber-500/40 bg-amber-50 text-amber-800';
}

function decisionTone(d?: string | null): string {
  const v = (d ?? '').toLowerCase();
  if (v === 'accepted') return 'text-green-700';
  if (v.includes('warning')) return 'text-[#9a6f00]';
  if (v === 'rejected') return 'text-red-700';
  return 'text-fg-muted';
}

export function SandboxControl({ locale, fixedProfile }: { locale: Locale; fixedProfile?: ProfileId }) {
  const [profile, setProfile] = useState<ProfileId>(fixedProfile ?? 'banco-tier1');
  const [pool, setPool] = useState<PoolItem[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loadingPool, setLoadingPool] = useState(false);
  const [sending, setSending] = useState(false);
  const [log, setLog] = useState<SendResult[]>([]);
  const [freq, setFreq] = useState<number | null>(null);
  const [rows, setRows] = useState(25);
  const [batch, setBatch] = useState<BatchState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const batchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const profileRef = useRef(profile);
  const selectedRef = useRef(selected);
  const poolRef = useRef(pool);
  profileRef.current = profile;
  selectedRef.current = selected;
  poolRef.current = pool;

  const inst = PROFILES.find((p) => p.id === profile)!;

  async function loadPool() {
    setLoadingPool(true);
    setSelected(null);
    try {
      const r = await fetch('/app/api/sandbox/tier1/pool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile, count: 12 }),
        cache: 'no-store',
      });
      const d = (await r.json()) as { candidates?: PoolItem[] };
      setPool(d.candidates ?? []);
    } catch {
      setPool([]);
    } finally {
      setLoadingPool(false);
    }
  }

  useEffect(() => {
    loadPool();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile]);

  async function doSend(opts: { payload?: Record<string, unknown>; count?: number }) {
    setSending(true);
    try {
      const r = await fetch('/app/api/sandbox/tier1/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: profileRef.current, ...opts }),
        cache: 'no-store',
      });
      const d = (await r.json()) as { results?: SendResult[]; error?: string };
      const results = d.results ?? (d.error ? [{ ok: false, http_status: null, error: d.error }] : []);
      setLog((prev) => [...results, ...prev].slice(0, 50));
    } catch (e) {
      setLog((prev) => [{ ok: false, http_status: null, error: String(e) }, ...prev].slice(0, 50));
    } finally {
      setSending(false);
    }
  }

  // "Send now" — selected pool complaint, else auto-pick (server generates one).
  function sendNow() {
    const sel = selectedRef.current;
    const item = sel != null ? poolRef.current.find((p) => p.idx === sel) : undefined;
    return doSend(item ? { payload: item.payload } : { count: 1 });
  }

  function toggleFreq(sec: number) {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (freq === sec) {
      setFreq(null);
      return;
    }
    setFreq(sec);
    sendNow();
    timerRef.current = setInterval(() => sendNow(), sec * 1000);
  }

  useEffect(() => () => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (batchTimerRef.current) clearInterval(batchTimerRef.current);
  }, []);

  // ---- Tier 2 batch ----
  function pollBatch(id: string) {
    const tick = async () => {
      try {
        const r = await fetch(`/app/api/sandbox/tier2/status?batch_id=${encodeURIComponent(id)}&profile=${profileRef.current}`, { cache: 'no-store' });
        const d = (await r.json()) as BatchState;
        setBatch((prev) => ({ ...prev, ...d }));
        if (d.status === 'complete' || d.status === 'failed') {
          if (batchTimerRef.current) {
            clearInterval(batchTimerRef.current);
            batchTimerRef.current = null;
          }
        }
      } catch {
        /* keep last */
      }
    };
    tick();
    batchTimerRef.current = setInterval(tick, 2000);
  }

  async function submitBatch() {
    setSubmitting(true);
    if (batchTimerRef.current) {
      clearInterval(batchTimerRef.current);
      batchTimerRef.current = null;
    }
    try {
      const r = await fetch('/app/api/sandbox/tier2/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: profileRef.current, rows }),
        cache: 'no-store',
      });
      const d = (await r.json()) as BatchState;
      setBatch(d);
      if (d.batch_id) pollBatch(d.batch_id);
    } catch (e) {
      setBatch({ error: String(e) });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {/* ---- Tier 1 panel ---- */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Send className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
            {bi(locale, 'Tier 1 — envío granular (NRT)', 'Tier 1 — granular send (NRT)')}
          </CardTitle>
          <Badge variant="default" className="font-mono">{bi(locale, 'API real', 'real API')}</Badge>
        </CardHeader>
        <CardBody className="space-y-3">
          {/* Institution selector — hidden on a per-bank page (locked to that bank). */}
          {fixedProfile ? (
            <div className="flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
              <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
              {bi(locale, 'Enviando como', 'Sending as')}
              <span className="text-brand-navy">{inst.label}</span>
              <span className="font-mono text-fg-muted">{inst.institution}</span>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="flex items-center gap-1 text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
                <Building2 className="h-3.5 w-3.5" aria-hidden="true" />
                {bi(locale, 'Institución que envía', 'Sending institution')}
              </span>
              {PROFILES.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setProfile(p.id)}
                  className={cn(
                    'rounded-sbs border px-2.5 py-1 text-xs font-medium',
                    profile === p.id ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy' : 'border-border bg-surface text-fg hover:bg-surface-subtle',
                  )}
                >
                  {p.label} <span className="font-mono text-2xs text-fg-muted">{p.institution}</span>
                </button>
              ))}
            </div>
          )}

          {/* Controls */}
          <div className="flex flex-wrap items-center gap-2 rounded-sbs border border-border bg-surface-subtle/40 p-2">
            <button
              type="button"
              onClick={sendNow}
              disabled={sending}
              className="inline-flex items-center gap-1 rounded-sbs border border-brand-navy bg-brand-navy px-3 py-1.5 text-xs font-medium text-fg-inverted hover:bg-brand-navy/90 disabled:opacity-50"
            >
              <Send className="h-3.5 w-3.5" aria-hidden="true" />
              {bi(locale, 'Enviar ahora', 'Send now')}
            </button>
            <span className="text-2xs text-fg-subtle">{bi(locale, 'Ráfaga', 'Burst')}</span>
            {[20, 50].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => doSend({ count: n })}
                disabled={sending}
                className="inline-flex items-center gap-1 rounded-sbs border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-brand-navy hover:bg-surface-subtle disabled:opacity-50"
              >
                <Zap className="h-3.5 w-3.5" aria-hidden="true" />
                {n}
              </button>
            ))}
            <span className="ml-2 text-2xs text-fg-subtle">{bi(locale, 'Frecuencia', 'Frequency')}</span>
            {FREQS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => toggleFreq(s)}
                className={cn(
                  'inline-flex items-center gap-1 rounded-sbs border px-2.5 py-1.5 text-xs font-medium',
                  freq === s ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy' : 'border-border bg-surface text-fg hover:bg-surface-subtle',
                )}
              >
                {freq === s ? <Pause className="h-3.5 w-3.5" aria-hidden="true" /> : <Play className="h-3.5 w-3.5" aria-hidden="true" />}
                {s}s
              </button>
            ))}
            {freq ? (
              <span className="flex items-center gap-1 text-2xs font-medium text-brand-cyan">
                <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-cyan opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-brand-cyan" /></span>
                {bi(locale, `enviando cada ${freq}s`, `sending every ${freq}s`)}
              </span>
            ) : null}
          </div>

          {/* Pool — synthetic queue the bank draws from; click to select */}
          <div>
            <div className="mb-1 flex items-center justify-between">
              <span className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">
                {bi(locale, `Cola del banco (${inst.label}) — elige uno o deja auto`, `Bank queue (${inst.label}) — pick one or leave auto`)}
              </span>
              <button type="button" onClick={loadPool} disabled={loadingPool} className="inline-flex items-center gap-1 rounded-sbs border border-border bg-surface px-2 py-0.5 text-2xs hover:bg-surface-subtle disabled:opacity-50">
                <RefreshCw className={cn('h-3 w-3', loadingPool && 'animate-spin')} aria-hidden="true" />
                {bi(locale, 'Regenerar', 'Regenerate')}
              </button>
            </div>
            <div className="max-h-56 overflow-auto rounded-sbs border border-border-subtle">
              <table className="w-full text-2xs">
                <thead className="sticky top-0 bg-surface-subtle text-fg-muted">
                  <tr>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Motivo', 'Motive')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Producto', 'Product')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Canal', 'Channel')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Sev.', 'Sev.')}</th>
                    <th className="px-2 py-1 text-right">{bi(locale, 'Enviar', 'Send')}</th>
                  </tr>
                </thead>
                <tbody>
                  {pool.map((c) => (
                    <tr
                      key={c.idx}
                      onClick={() => setSelected((s) => (s === c.idx ? null : c.idx))}
                      className={cn('cursor-pointer border-t border-border-subtle hover:bg-surface-subtle', selected === c.idx && 'bg-brand-cyan/10')}
                    >
                      <td className="px-2 py-1 font-mono">{c.motive}</td>
                      <td className="px-2 py-1">{c.product}</td>
                      <td className="px-2 py-1">{c.channel}</td>
                      <td className="px-2 py-1">{c.severity}</td>
                      <td className="px-2 py-1 text-right">
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); doSend({ payload: c.payload }); }}
                          disabled={sending}
                          className="rounded-sbs border border-border bg-surface px-2 py-0.5 text-2xs text-brand-navy hover:border-brand-cyan disabled:opacity-50"
                        >
                          {bi(locale, 'Enviar', 'Send')}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {pool.length === 0 ? (
                    <tr><td colSpan={5} className="px-2 py-3 text-center text-fg-muted">{loadingPool ? bi(locale, 'Generando…', 'Generating…') : bi(locale, 'Sin candidatos.', 'No candidates.')}</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </div>

          {/* Real responses */}
          <div>
            <span className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{bi(locale, 'Respuestas reales del API', 'Real API responses')}</span>
            <div className="mt-1 max-h-56 overflow-auto rounded-sbs border border-border-subtle">
              <table className="w-full text-2xs">
                <thead className="sticky top-0 bg-surface-subtle text-fg-muted">
                  <tr>
                    <th className="px-2 py-1 text-left">HTTP</th>
                    <th className="px-2 py-1 text-left">complaint_id</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Verdicto DQ', 'DQ verdict')}</th>
                    <th className="px-2 py-1 text-left">{bi(locale, 'Motivo', 'Motive')}</th>
                  </tr>
                </thead>
                <tbody>
                  {log.map((r, i) => (
                    <tr key={i} className="border-t border-border-subtle">
                      <td className={cn('px-2 py-1 font-mono', r.ok ? 'text-green-700' : 'text-red-700')}>{r.http_status ?? 'ERR'}</td>
                      <td className="px-2 py-1 font-mono">
                        {r.complaint_id ? (
                          <Link href={`/processing/${r.complaint_id}`} className="inline-flex items-center gap-1 text-fg-link hover:underline">
                            {r.complaint_id}
                            <ExternalLink className="h-3 w-3" aria-hidden="true" />
                          </Link>
                        ) : (
                          <span className="text-fg-muted">{r.error ? r.error.slice(0, 40) : '—'}</span>
                        )}
                      </td>
                      <td className={cn('px-2 py-1 font-mono', decisionTone(r.decision))}>{r.decision ?? '—'}</td>
                      <td className="px-2 py-1 font-mono">{r.motive ?? '—'}</td>
                    </tr>
                  ))}
                  {log.length === 0 ? (
                    <tr><td colSpan={4} className="px-2 py-3 text-center text-fg-muted">{bi(locale, 'Aún no se ha enviado nada.', 'Nothing sent yet.')}</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-2xs italic text-fg-subtle">
              {bi(
                locale,
                'Cada fila es una respuesta real del endpoint Tier-1 firmado (OAuth + HMAC + mTLS). El verdicto DQ es la validación Anexo 1-A real; el reclamo se persiste y aparece en el banner aunque el verdicto sea "rejected".',
                'Each row is a real response from the signed Tier-1 endpoint (OAuth + HMAC + mTLS). The DQ verdict is the real Anexo 1-A validation; the complaint is persisted and appears in the banner even when the verdict is "rejected".',
              )}
            </p>
          </div>
        </CardBody>
      </Card>

      {/* ---- Tier 2 panel ---- */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <FileUp className="h-4 w-4 text-brand-gold" aria-hidden="true" />
            {bi(locale, 'Tier 2 — lote CSV (batch)', 'Tier 2 — CSV batch')}
          </CardTitle>
          <Badge variant="default" className="font-mono">{bi(locale, 'API real', 'real API')}</Badge>
        </CardHeader>
        <CardBody className="space-y-3">
          <p className="text-2xs text-fg-muted">
            {bi(
              locale,
              `Genera un CSV Anexo 1-A real y lo sube por el endpoint REAL POST /v1/batches (OAuth batch:upload + HMAC multipart + mTLS). Institución: ${inst.label} (${inst.institution}).`,
              `Builds a real Anexo 1-A CSV and uploads it through the REAL POST /v1/batches endpoint (OAuth batch:upload + multipart HMAC + mTLS). Institution: ${inst.label} (${inst.institution}).`,
            )}
          </p>

          <div className="flex flex-wrap items-center gap-2 rounded-sbs border border-border bg-surface-subtle/40 p-2">
            <span className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{bi(locale, 'Filas', 'Rows')}</span>
            {[10, 25, 50, 100].map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setRows(n)}
                className={cn(
                  'rounded-sbs border px-2.5 py-1 text-xs font-medium tabular-nums',
                  rows === n ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy' : 'border-border bg-surface text-fg hover:bg-surface-subtle',
                )}
              >
                {n}
              </button>
            ))}
            <button
              type="button"
              onClick={submitBatch}
              disabled={submitting}
              className="ml-auto inline-flex items-center gap-1 rounded-sbs border border-brand-navy bg-brand-navy px-3 py-1.5 text-xs font-medium text-fg-inverted hover:bg-brand-navy/90 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <FileUp className="h-3.5 w-3.5" aria-hidden="true" />}
              {bi(locale, `Generar y enviar ${rows} filas`, `Generate & send ${rows} rows`)}
            </button>
          </div>

          {/* Real batch status */}
          {batch ? (
            <div className="space-y-2 rounded-sbs border border-border p-3">
              {batch.error ? (
                <p className="text-xs text-red-700">{batch.error}</p>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn('inline-flex items-center gap-1 rounded-sbs border px-2 py-0.5 text-2xs font-semibold uppercase', batchTone(batch.status))}>
                      {batch.status === 'complete' ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : batch.status === 'failed' ? null : <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />}
                      {batch.status ?? '—'}
                    </span>
                    {batch.http_status ? <span className="font-mono text-2xs text-fg-muted">HTTP {batch.http_status}</span> : null}
                    {batch.batch_id ? <span className="font-mono text-2xs text-fg-muted">{batch.batch_id}</span> : null}
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-sbs border border-border-subtle bg-surface-subtle/40 p-2">
                      <div className="text-2xs uppercase tracking-wide text-fg-subtle">{bi(locale, 'Enviadas', 'Submitted')}</div>
                      <div className="font-mono text-lg tabular-nums text-brand-navy">{batch.row_count_submitted ?? '—'}</div>
                    </div>
                    <div className="rounded-sbs border border-green-600/30 bg-green-50 p-2">
                      <div className="text-2xs uppercase tracking-wide text-green-700">{bi(locale, 'Aceptadas', 'Accepted')}</div>
                      <div className="font-mono text-lg tabular-nums text-green-700">{batch.row_count_accepted ?? '—'}</div>
                    </div>
                    <div className="rounded-sbs border border-red-600/30 bg-red-50 p-2">
                      <div className="text-2xs uppercase tracking-wide text-red-700">{bi(locale, 'Rechazadas', 'Rejected')}</div>
                      <div className="font-mono text-lg tabular-nums text-red-700">{batch.row_count_rejected ?? '—'}</div>
                    </div>
                  </div>

                  {/* Per-complaint records — the real rows the batch carried; accepted
                      rows are persisted (linkable), rejected rows come from the real
                      /rejections endpoint. Mirrors the Tier-1 responses table. */}
                  {batch.rows && batch.rows.length ? (() => {
                    const rejected = new Set(batch.rejected_rows ?? []);
                    const terminal = batch.status === 'complete' || batch.status === 'failed';
                    const shown = batch.rows.slice(0, BATCH_ROW_CAP);
                    return (
                      <div>
                        <div className="mb-1 flex items-center justify-between">
                          <span className="text-2xs font-semibold uppercase tracking-wide text-fg-subtle">{bi(locale, 'Reclamos del lote (real)', 'Batch complaints (real)')}</span>
                          {batch.rows.length > BATCH_ROW_CAP ? (
                            <span className="text-2xs text-fg-muted">{bi(locale, `mostrando ${BATCH_ROW_CAP} de ${batch.rows.length}`, `showing ${BATCH_ROW_CAP} of ${batch.rows.length}`)}</span>
                          ) : null}
                        </div>
                        <div className="max-h-56 overflow-auto rounded-sbs border border-border-subtle">
                          <table className="w-full text-2xs">
                            <thead className="sticky top-0 bg-surface-subtle text-fg-muted">
                              <tr>
                                <th className="px-2 py-1 text-left">complaint_id</th>
                                <th className="px-2 py-1 text-left">{bi(locale, 'Verdicto DQ', 'DQ verdict')}</th>
                                <th className="px-2 py-1 text-left">{bi(locale, 'Motivo', 'Motive')}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {shown.map((r, i) => {
                                const isRejected = rejected.has(i);
                                const verdict = !terminal ? bi(locale, 'procesando…', 'processing…') : isRejected ? 'rejected' : 'accepted';
                                return (
                                  <tr key={r.complaint_id} className="border-t border-border-subtle">
                                    <td className="px-2 py-1 font-mono">
                                      {terminal && !isRejected ? (
                                        <Link href={`/processing/${r.complaint_id}`} className="inline-flex items-center gap-1 text-fg-link hover:underline">
                                          {r.complaint_id}
                                          <ExternalLink className="h-3 w-3" aria-hidden="true" />
                                        </Link>
                                      ) : (
                                        <span className="text-fg">{r.complaint_id}</span>
                                      )}
                                    </td>
                                    <td className={cn('px-2 py-1 font-mono', terminal ? decisionTone(verdict) : 'text-fg-muted')}>{verdict}</td>
                                    <td className="px-2 py-1 font-mono">{r.motivo ?? '—'}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })() : null}
                </>
              )}
            </div>
          ) : (
            <p className="py-4 text-center text-xs text-fg-muted">{bi(locale, 'Aún no se ha enviado ningún lote.', 'No batch submitted yet.')}</p>
          )}

          <p className="text-2xs italic text-fg-subtle">
            {bi(
              locale,
              'El lote pasa por el worker real (pending → processing → complete). Las filas aceptadas se persisten como reclamos y aparecen en el banner.',
              'The batch runs through the real worker (pending → processing → complete). Accepted rows are persisted as complaints and appear in the banner.',
            )}
          </p>
        </CardBody>
      </Card>
    </div>
  );
}
