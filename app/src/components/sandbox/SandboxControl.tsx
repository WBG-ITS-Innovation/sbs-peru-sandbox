/* eslint-disable i18next/no-literal-string */
'use client';

import { Building2, ExternalLink, Pause, Play, RefreshCw, Send, Zap } from 'lucide-react';
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

function decisionTone(d?: string | null): string {
  const v = (d ?? '').toLowerCase();
  if (v === 'accepted') return 'text-green-700';
  if (v.includes('warning')) return 'text-[#9a6f00]';
  if (v === 'rejected') return 'text-red-700';
  return 'text-fg-muted';
}

export function SandboxControl({ locale }: { locale: Locale }) {
  const [profile, setProfile] = useState<ProfileId>('banco-tier1');
  const [pool, setPool] = useState<PoolItem[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loadingPool, setLoadingPool] = useState(false);
  const [sending, setSending] = useState(false);
  const [log, setLog] = useState<SendResult[]>([]);
  const [freq, setFreq] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
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
  }, []);

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
          {/* Institution selector */}
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
    </div>
  );
}
