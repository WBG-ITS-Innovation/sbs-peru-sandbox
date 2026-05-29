/* eslint-disable i18next/no-literal-string */
'use client';

import { BarChart3, FileText, Flag, Table2 } from 'lucide-react';
import { useState } from 'react';

import { AggregateTables } from '@/components/persona/AggregateTables';
import { AggregatesDocs } from '@/components/persona/AggregatesDocs';
import { AggregatesGraphs } from '@/components/persona/AggregatesGraphs';
import { LiveIngestionBanner } from '@/components/persona/LiveIngestionBanner';
import { RedFlags } from '@/components/persona/RedFlags';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { cn } from '@/lib/cn';

// Top-level IA for the aggregates surface: four tabs over the shared
// live-ingestion banner. Replaces the old fabricated AggregatesView.
//   Tablas        — View 1 grouped-aggregate tables (real SQL)
//   Gráficos      — recharts over the real aggregate endpoint
//   Alertas rojas — View 2 flagged-pattern tables
//   Documentación — full agentic-workflow docs

type TopTab = 'tablas' | 'graficos' | 'alertas' | 'docs';

const TOP_TABS: { id: TopTab; es: string; en: string; Icon: typeof Table2 }[] = [
  { id: 'tablas', es: 'Tablas', en: 'Tables', Icon: Table2 },
  { id: 'graficos', es: 'Gráficos', en: 'Charts', Icon: BarChart3 },
  { id: 'alertas', es: 'Alertas rojas', en: 'Red flags', Icon: Flag },
  { id: 'docs', es: 'Documentación', en: 'Documentation', Icon: FileText },
];

export function AggregatesWorkspace({ locale }: { locale: Locale }) {
  const [tab, setTab] = useState<TopTab>('tablas');
  const [presetMotivo, setPresetMotivo] = useState<string | null>(null);

  const pickMotivo = (motivo: string) => {
    setPresetMotivo(motivo);
    setTab('tablas');
  };

  return (
    <div className="mx-auto w-full max-w-screen-2xl space-y-4 p-4">
      <h1 className="text-xl font-semibold tracking-tight text-brand-navy">
        {bi(locale, 'Agregados y conducta de mercado', 'Aggregates & market conduct')}
      </h1>

      <LiveIngestionBanner locale={locale} />

      <div className="flex gap-1 border-b border-border">
        {TOP_TABS.map((t) => {
          const Icon = t.Icon;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                'flex items-center gap-1.5 rounded-t-sbs border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                tab === t.id
                  ? 'border-brand-cyan text-brand-navy'
                  : 'border-transparent text-fg-muted hover:text-fg',
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" />
              {bi(locale, t.es, t.en)}
            </button>
          );
        })}
      </div>

      {tab === 'tablas' ? <AggregateTables locale={locale} presetMotivo={presetMotivo} /> : null}
      {tab === 'graficos' ? <AggregatesGraphs locale={locale} onPickMotivo={pickMotivo} /> : null}
      {tab === 'alertas' ? <RedFlags locale={locale} /> : null}
      {tab === 'docs' ? <AggregatesDocs locale={locale} /> : null}
    </div>
  );
}
