'use client';

import { CheckCircle2, Pause, Play } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

// Live ingestion banner. NO fabricated data: it polls the REAL feed
// (/app/api/aggregates/feed → /v1/internal/findings) every 10s and animates
// the most-recent actually-ingested complaint through the per-complaint flow.
// SSR-safe: the initial render is a fixed placeholder (no Math.random), and
// every live value is set in useEffect after mount — so server and client
// markup match and there is no hydration mismatch.

const POLL_MS = 10_000; // 10s cadence (matches nrt_feed default)
const STAGE_MS = 900; // per-step animation when a new complaint arrives

interface Finding {
  complaint_id: string;
  institution_name?: string;
  classification?: string;
  severity?: string;
  received_at?: string;
}

function stepDesc(locale: Locale, key: string): string {
  switch (key) {
    case 'recv':
      return bi(
        locale,
        'Recepción: el reclamo entra por el canal Tier-1 (POST firmado: OAuth + HMAC + mTLS).',
        'Reception: the complaint arrives over the Tier-1 channel (signed POST: OAuth + HMAC + mTLS).',
      );
    case 'dv':
      return bi(
        locale,
        'DIValeVale: valida el formato Anexo 1-A y la calidad de datos antes de aceptar (por reclamo).',
        'DIValeVale: validates Anexo 1-A format and data quality before acceptance (per complaint).',
      );
    case 'tri':
      return bi(
        locale,
        'Triage: clasifica el motivo y detecta señales del sistema (clasificador basado en reglas; BERT en producción).',
        'Triage: classifies the motive and detects system signals (rules-based classifier; BERT in production).',
      );
    case 'pool':
      return bi(
        locale,
        'Pool de agregados: el reclamo se suma al pool que los agentes agregados escanean cada 60s.',
        'Aggregate pool: the complaint joins the pool the aggregate agents scan every 60s.',
      );
    default:
      return '';
  }
}

function makeStages(locale: Locale, f: Finding | null): { key: string; label: string; out: string }[] {
  return [
    { key: 'recv', label: bi(locale, 'Recibiendo', 'Receiving'), out: f?.complaint_id ?? '—' },
    { key: 'dv', label: 'DIValeVale', out: f ? bi(locale, 'Validado ✓', 'Validated ✓') : '—' },
    {
      key: 'tri',
      label: 'Triage',
      out: f ? `${f.classification ?? '—'} · ${f.severity ?? '—'}` : '—',
    },
    { key: 'pool', label: bi(locale, 'Pool de agregados', 'Aggregate pool'), out: f ? bi(locale, 'Añadido ✓', 'Added ✓') : '—' },
  ];
}

export function LiveIngestionBanner({ locale }: { locale: Locale }) {
  // Initial state is deterministic (no random) → SSR === first client render.
  const [latest, setLatest] = useState<Finding | null>(null);
  const [step, setStep] = useState(0);
  const [paused, setPaused] = useState(false);
  const lastId = useRef<string | null>(null);

  // Poll the real feed for the most recently ingested complaint.
  useEffect(() => {
    if (paused) return undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const r = await fetch('/app/api/aggregates/feed', { cache: 'no-store' });
        const d = (await r.json()) as { items?: Finding[] };
        const items = (d.items ?? []).filter((i) => i.received_at);
        items.sort((a, b) => (b.received_at ?? '').localeCompare(a.received_at ?? ''));
        const top = items[0] ?? null;
        if (!cancelled && top && top.complaint_id !== lastId.current) {
          lastId.current = top.complaint_id;
          setLatest(top);
          setStep(0); // animate the new arrival from the first step
        }
      } catch {
        /* keep last state */
      }
    };
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [paused]);

  // Advance the per-complaint flow animation for the current complaint.
  useEffect(() => {
    if (paused || latest == null || step >= 4) return undefined;
    const id = setTimeout(() => setStep((s) => Math.min(4, s + 1)), STAGE_MS);
    return () => clearTimeout(id);
  }, [paused, latest, step]);

  const stages = makeStages(locale, latest);
  const done = step >= stages.length;

  return (
    <div className="sticky top-0 z-20 rounded-sbs border border-border bg-surface px-3 py-2 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            {!paused && latest ? (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-cyan opacity-75" />
            ) : null}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${paused || !latest ? 'bg-neutral-400' : 'bg-brand-cyan'}`} />
          </span>
          <h2 className="text-sm font-semibold tracking-tight text-fg">
            {bi(locale, 'Reclamos entrando al sistema', 'Live ingestion')}
          </h2>
          <span className="font-mono text-2xs tabular-nums text-fg-subtle">
            {latest ? latest.complaint_id : bi(locale, 'esperando reclamos…', 'waiting for complaints…')}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setPaused((p) => !p)}
          className="flex items-center gap-1 rounded-sbs border border-border px-2 py-1 text-2xs font-medium text-fg hover:bg-surface-subtle"
        >
          {paused ? <Play className="h-3 w-3" aria-hidden="true" /> : <Pause className="h-3 w-3" aria-hidden="true" />}
          {paused ? bi(locale, 'Reanudar', 'Resume') : bi(locale, 'Pausar', 'Pause')}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-stretch gap-1.5">
        {stages.map((st, i) => {
          const active = latest != null && i === step && !done;
          const complete = latest != null && (i < step || done);
          const tone = active
            ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy animate-pulse'
            : complete
              ? 'border-green-600/40 bg-green-50 text-green-700'
              : 'border-border bg-surface-subtle text-fg-subtle';
          return (
            <div
              key={st.key}
              title={stepDesc(locale, st.key)}
              className={`min-w-[120px] flex-1 cursor-help rounded-sbs border px-2 py-1 transition-colors ${tone}`}
            >
              <div className="flex items-center gap-1 text-2xs font-semibold">
                {complete ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : <span className="font-mono">{i + 1}</span>}
                {st.label}
              </div>
              <div className="mt-0.5 truncate font-mono text-2xs tabular-nums">
                {latest != null && (active || complete) ? st.out : '…'}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
