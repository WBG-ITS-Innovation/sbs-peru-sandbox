'use client';

import { CheckCircle2, Pause, Play } from 'lucide-react';
import { useEffect, useState } from 'react';

import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

const STAGE_MS = 1200;
const MOTIVOS = ['cobros_indebidos', 'fraude', 'calidad_servicio', 'informacion'];

interface Stage {
  key: string;
  label: string;
  out: string;
}
interface Scenario {
  id: string;
  stages: Stage[];
}

function makeScenario(locale: Locale): Scenario {
  const r = Math.random;
  const id = `BCO-2026-${Math.floor(100000 + r() * 900000)}`;
  const validated = r() > 0.1;
  const motivo = MOTIVOS[Math.floor(r() * MOTIVOS.length)];
  const confidence = (0.78 + r() * 0.17).toFixed(2);
  const systemSignal = r() > 0.5;

  // Per-complaint flow ONLY (real-time). Pattern / Investigation / Lupaman
  // run on the aggregate pool every 60s, not per complaint — see the
  // "Aggregate analysis cycle" section below.
  const stages: Stage[] = [
    { key: 'recv', label: bi(locale, 'Recibiendo', 'Receiving'), out: id },
    { key: 'dv', label: 'DIValeVale', out: validated ? bi(locale, 'Validado ✓', 'Validated ✓') : 'INSUFFICIENT' },
    {
      key: 'tri',
      label: 'Triage',
      out: `${motivo} · ${confidence}${systemSignal ? ' · system_signal' : ''}`,
    },
    { key: 'pool', label: bi(locale, 'Pool de agregados', 'Aggregate pool'), out: bi(locale, 'Añadido ✓', 'Added ✓') },
  ];
  return { id, stages };
}

export function LiveIngestionBanner({ locale }: { locale: Locale }) {
  const [scenario, setScenario] = useState<Scenario>(() => makeScenario(locale));
  const [step, setStep] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return undefined;
    const id = setInterval(() => {
      setStep((s) => {
        if (s >= scenario.stages.length) {
          setScenario(makeScenario(locale));
          return 0;
        }
        return s + 1;
      });
    }, STAGE_MS);
    return () => clearInterval(id);
  }, [paused, scenario, locale]);

  const done = step >= scenario.stages.length;

  return (
    <div className="sticky top-0 z-20 rounded-sbs border border-border bg-surface px-3 py-2 shadow-sm">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            {!paused ? (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-cyan opacity-75" />
            ) : null}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${paused ? 'bg-neutral-400' : 'bg-brand-cyan'}`} />
          </span>
          <h2 className="text-sm font-semibold tracking-tight text-fg">
            {bi(locale, 'Reclamos entrando al sistema', 'Live ingestion')}
          </h2>
          <span className="font-mono text-2xs tabular-nums text-fg-subtle">{scenario.id}</span>
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
        {scenario.stages.map((st, i) => {
          const active = i === step && !done;
          const complete = i < step || done;
          const tone = active
            ? 'border-brand-cyan bg-brand-cyan/10 text-brand-navy animate-pulse'
            : complete
              ? 'border-green-600/40 bg-green-50 text-green-700'
              : 'border-border bg-surface-subtle text-fg-subtle';
          return (
            <div key={st.key} className={`min-w-[120px] flex-1 rounded-sbs border px-2 py-1 transition-colors ${tone}`}>
              <div className="flex items-center gap-1 text-2xs font-semibold">
                {complete ? <CheckCircle2 className="h-3 w-3" aria-hidden="true" /> : <span className="font-mono">{i + 1}</span>}
                {st.label}
              </div>
              <div className="mt-0.5 truncate font-mono text-2xs tabular-nums">
                {active || complete ? st.out : '…'}
              </div>
            </div>
          );
        })}
        {done ? (
          <div className="flex min-w-[120px] flex-1 items-center justify-center rounded-sbs border border-green-600/40 bg-green-50 px-2 py-1 text-2xs font-semibold text-green-700">
            <CheckCircle2 className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            {bi(locale, 'Procesado en 2.1s ✓', 'Processed in 2.1s ✓')}
          </div>
        ) : null}
      </div>

      <p className="mt-1.5 text-2xs italic text-fg-muted">
        {bi(
          locale,
          'Investigation y Lupaman procesan el pool cada 60s — ver sección de análisis agregado abajo',
          'Investigation and Lupaman process the pool every 60s — see the aggregate analysis section below',
        )}
      </p>
    </div>
  );
}
