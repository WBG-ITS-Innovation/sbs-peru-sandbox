import { AlertTriangle, CheckCircle2, Info, TrendingUp } from 'lucide-react';
import type { ReactNode } from 'react';

import type { Tone } from '@/components/persona/AggregationStrip';

export interface Insight {
  tone: Tone;
  headline: string;
  body: string;
  meta?: string;
  /** Optional inline action (e.g. an approve button). */
  action?: ReactNode;
}

const ICON: Record<Tone, typeof Info> = {
  red: AlertTriangle,
  amber: TrendingUp,
  green: CheckCircle2,
  neutral: Info,
};

const ICON_COLOR: Record<Tone, string> = {
  red: 'text-red-600',
  amber: 'text-amber-500',
  green: 'text-green-600',
  neutral: 'text-brand-cyan',
};

// Generated-insight card: 2–4 composed "so what" insights for a persona.
export function InsightsPanel({ title, insights }: { title: string; insights: Insight[] }) {
  if (insights.length === 0) return null;
  return (
    <section className="rounded-sbs border border-border bg-surface">
      <header className="border-b border-border-subtle px-3 py-2">
        <h2 className="text-sm font-semibold tracking-tight text-fg">{title}</h2>
      </header>
      <ul className="divide-y divide-border-subtle">
        {insights.map((ins, i) => {
          const Icon = ICON[ins.tone];
          return (
            <li key={`${ins.headline}-${i}`} className="flex gap-2.5 px-3 py-2.5">
              <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${ICON_COLOR[ins.tone]}`} aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold leading-snug text-brand-navy">{ins.headline}</p>
                <p className="mt-0.5 text-xs leading-snug text-fg">{ins.body}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {ins.meta ? (
                    <span className="font-mono text-2xs text-fg-subtle">{ins.meta}</span>
                  ) : null}
                  {ins.action}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
