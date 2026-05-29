import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react';

export type Tone = 'green' | 'amber' | 'red' | 'neutral';
export type Trend = 'up' | 'down' | 'flat';

export interface Tile {
  label: string;
  /** Muted secondary label (English gloss or unit). */
  sublabel?: string;
  value: string | number;
  trend?: Trend;
  tone?: Tone;
}

const BORDER: Record<Tone, string> = {
  green: 'border-l-green-600',
  amber: 'border-l-amber-500',
  red: 'border-l-red-600',
  neutral: 'border-l-brand-navy',
};

const DOT: Record<Tone, string> = {
  green: 'text-green-600',
  amber: 'text-amber-500',
  red: 'text-red-600',
  neutral: 'text-fg-subtle',
};

function TrendIcon({ trend, tone }: { trend?: Trend; tone: Tone }) {
  if (!trend) return null;
  const cls = `h-3.5 w-3.5 ${DOT[tone]}`;
  if (trend === 'up') return <ArrowUpRight className={cls} aria-hidden="true" />;
  if (trend === 'down') return <ArrowDownRight className={cls} aria-hidden="true" />;
  return <ArrowRight className={cls} aria-hidden="true" />;
}

// Horizontal row of 4 metric tiles at the top of a dashboard.
// Bloomberg-density: small labels, tabular monospace numerals, tight padding.
export function AggregationStrip({ tiles }: { tiles: Tile[] }) {
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
      {tiles.map((t, i) => {
        const tone = t.tone ?? 'neutral';
        return (
          <div
            key={`${t.label}-${i}`}
            className={`rounded-sbs border border-border border-l-4 ${BORDER[tone]} bg-surface px-3 py-2`}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="truncate text-2xs uppercase tracking-wide text-fg-subtle">
                {t.label}
              </span>
              <TrendIcon trend={t.trend} tone={tone} />
            </div>
            <div className="mt-0.5 font-mono text-2xl tabular-nums leading-none text-fg">
              {t.value}
            </div>
            {t.sublabel ? (
              <div className="mt-0.5 text-2xs italic text-fg-muted">{t.sublabel}</div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
