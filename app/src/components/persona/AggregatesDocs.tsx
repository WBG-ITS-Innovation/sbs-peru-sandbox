/* eslint-disable i18next/no-literal-string */
'use client';

import { useEffect, useState } from 'react';

import { AgentFlowsExplainer } from '@/components/persona/AgentFlowsExplainer';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

// Documentación tab — the full agentic-workflow explainer (per-complaint +
// aggregate flows, all agents, the ReAct loop), moved off the main surface.
// poolSize is the real total complaint count; the per-window figures inside
// the walkthroughs are illustrative (flagged below).

export function AggregatesDocs({ locale }: { locale: Locale }) {
  const [total, setTotal] = useState(0);

  useEffect(() => {
    fetch('/app/api/aggregates/trend', { cache: 'no-store' })
      .then((r) => r.json())
      .then((d: { by_motivo?: { n_complaints: number }[] }) =>
        setTotal((d.by_motivo ?? []).reduce((a, m) => a + m.n_complaints, 0)),
      )
      .catch(() => undefined);
  }, []);

  return (
    <div className="space-y-3">
      <p className="rounded-sbs border border-border bg-surface-subtle/50 p-3 text-xs text-fg-muted">
        {bi(
          locale,
          'Documentación del flujo agentico. El total de reclamos es real; las cifras por ventana dentro de los recorridos son ilustrativas.',
          'Agentic-workflow documentation. The complaint total is real; the per-window figures inside the walkthroughs are illustrative.',
        )}
      </p>
      <AgentFlowsExplainer locale={locale} poolSize={total} highCount={0} />
    </div>
  );
}
