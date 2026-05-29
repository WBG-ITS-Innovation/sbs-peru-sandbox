import { safeGet } from '@/auth/persona-server';
import { AggregationStrip, type Tile } from '@/components/persona/AggregationStrip';
import { InsightsPanel, type Insight } from '@/components/persona/InsightsPanel';
import { ActionBar, AgentGrid, Section } from '@/components/persona/primitives';
import { Badge } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { personaTitle, type PersonaConfig } from '@/lib/persona';
import type {
  ActionsResponse,
  AgentHealthItem,
  AgentsResponse,
  ErrorTail,
  IngestionLagItem,
  QueueDepth,
  WebhookHealth,
} from '@/types/persona-dashboards';

function lagVariant(s: string): 'low' | 'medium' | 'high' {
  if (s === 'RED') return 'high';
  if (s === 'AMBER') return 'medium';
  return 'low';
}

export async function SbsItDashboard({
  persona,
  locale,
}: {
  persona: PersonaConfig;
  locale: Locale;
}) {
  const [lag, health, webhooks, queues, errors, actions, agents] = await Promise.all([
    safeGet<{ items: IngestionLagItem[] }>(persona, '/v1/internal/ops/ingestion_lag', { items: [] }),
    safeGet<{ items: AgentHealthItem[] }>(persona, '/v1/internal/ops/agent_health', { items: [] }),
    safeGet<WebhookHealth>(persona, '/v1/internal/ops/webhook_health', {
      total: 0,
      by_status: {},
      attempt_histogram: {},
      last_failures: [],
    }),
    safeGet<QueueDepth>(persona, '/v1/internal/ops/queue_depth', { queues: {} }),
    safeGet<ErrorTail>(persona, '/v1/internal/ops/error_tail', { errors: [] }),
    safeGet<ActionsResponse>(persona, '/v1/internal/cockpit/actions', { actions: [], total: 0 }),
    safeGet<AgentsResponse>(persona, '/v1/internal/cockpit/agents?window=24h', {
      agents: [],
      window: '24h',
      computed_at: '',
    }),
  ]);

  const avgSuccess =
    health.items.length > 0
      ? health.items.reduce((s, a) => s + a.success_rate_24h, 0) / health.items.length
      : 1;
  const successPct = Math.round(avgSuccess * 100);
  const worstAgent = [...health.items].sort((a, b) => a.success_rate_24h - b.success_rate_24h)[0];
  const maxLag = lag.items.reduce((m, i) => Math.max(m, i.lag_hours), 0);
  const anyRedLag = lag.items.some((i) => i.status === 'RED');
  const anyAmberLag = lag.items.some((i) => i.status === 'AMBER');

  const tiles: Tile[] = [
    {
      label: bi(locale, 'Éxito de agentes 24h', 'Agent success 24h'),
      value: `${successPct}%`,
      tone: successPct >= 95 ? 'green' : successPct >= 85 ? 'amber' : 'red',
    },
    {
      label: bi(locale, 'Webhooks fallidos', 'Failed webhooks'),
      value: webhooks.last_failures.length,
      tone: webhooks.last_failures.length > 0 ? 'red' : 'green',
    },
    {
      label: bi(locale, 'Retraso máx. ingesta', 'Max ingestion lag'),
      sublabel: bi(locale, 'horas', 'hours'),
      value: maxLag.toFixed(1),
      tone: anyRedLag ? 'red' : anyAmberLag ? 'amber' : 'green',
    },
    {
      label: bi(locale, 'Errores recientes', 'Recent errors'),
      value: errors.errors.length,
      tone: errors.errors.length > 3 ? 'red' : errors.errors.length > 0 ? 'amber' : 'green',
    },
  ];

  const insights: Insight[] = [
    {
      tone: worstAgent && worstAgent.success_rate_24h < 0.9 ? 'amber' : 'green',
      headline: worstAgent
        ? bi(
            locale,
            `Agente ${worstAgent.agent}: ${Math.round(worstAgent.success_rate_24h * 100)}% de éxito 24h`,
            `Agent ${worstAgent.agent}: ${Math.round(worstAgent.success_rate_24h * 100)}% success 24h`,
          )
        : bi(locale, 'Agentes sin datos', 'No agent data'),
      body: bi(
        locale,
        'Es la tasa de éxito más baja entre los agentes. Sin incidentes anotados aún.',
        'This is the lowest success rate across agents. No incidents annotated yet.',
      ),
      meta: `${health.items.length} ${bi(locale, 'agentes', 'agents')}`,
    },
    {
      tone: anyRedLag ? 'red' : anyAmberLag ? 'amber' : 'green',
      headline: bi(
        locale,
        `Retraso de ingesta máximo: ${maxLag.toFixed(1)}h`,
        `Max ingestion lag: ${maxLag.toFixed(1)}h`,
      ),
      body: bi(
        locale,
        'Instituciones por encima de su cadencia esperada de envío.',
        'Institutions above their expected submission cadence.',
      ),
      meta: `${lag.items.length} ${bi(locale, 'instituciones', 'institutions')} · ${webhooks.last_failures.length} ${bi(locale, 'fallos webhook', 'webhook failures')}`,
    },
  ];

  return (
    <div className="mx-auto w-full max-w-screen-2xl space-y-4 p-4">
      <header>
        <h1 className="text-xl font-semibold tracking-tight text-fg">
          {persona.name} · {personaTitle(persona, locale)}
        </h1>
        <p className="text-xs text-fg-muted">
          {bi(locale, 'Operaciones de plataforma · sin datos de negocio', 'Platform operations · no business data')}
        </p>
      </header>

      <AggregationStrip tiles={tiles} />

      <InsightsPanel title={bi(locale, 'Insights', 'Insights')} insights={insights} />

      <Section
        title={bi(locale, 'Monitoreo de agentes (técnico)', 'Agent monitoring (technical)')}
        locale={locale}
      >
        <AgentGrid agents={agents.agents} locale={locale} opsView />
      </Section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Section title={bi(locale, 'Retraso de ingesta', 'Ingestion lag')} locale={locale}>
          {lag.items.length === 0 ? (
            <p className="text-xs text-fg-muted">—</p>
          ) : (
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-2xs uppercase tracking-wide text-fg-subtle">
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Institución', 'Institution')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Retraso (h)', 'Lag (h)')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Estado', 'Status')}</th>
                </tr>
              </thead>
              <tbody>
                {lag.items.map((i) => (
                  <tr key={i.institution_id} className="border-b border-border-subtle">
                    <td className="px-2 py-1.5 font-mono text-fg">{i.institution_id}</td>
                    <td className="px-2 py-1.5 font-mono text-fg">{i.lag_hours.toFixed(1)}</td>
                    <td className="px-2 py-1.5">
                      <Badge variant={lagVariant(i.status)}>{i.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>

        <Section title={bi(locale, 'Salud de agentes', 'Agent health')} locale={locale}>
          {health.items.length === 0 ? (
            <p className="text-xs text-fg-muted">—</p>
          ) : (
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-2xs uppercase tracking-wide text-fg-subtle">
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Agente', 'Agent')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Ejec. 24h', 'Runs 24h')}</th>
                  <th className="px-2 py-1.5 font-medium">{bi(locale, 'Éxito', 'Success')}</th>
                  <th className="px-2 py-1.5 font-medium">{'p95'}</th>
                </tr>
              </thead>
              <tbody>
                {health.items.map((a) => (
                  <tr key={a.agent} className="border-b border-border-subtle">
                    <td className="px-2 py-1.5 font-mono text-fg">{a.agent}</td>
                    <td className="px-2 py-1.5 font-mono text-fg">{a.runs_24h}</td>
                    <td className="px-2 py-1.5 font-mono text-fg">
                      {Math.round(a.success_rate_24h * 100)}%
                    </td>
                    <td className="px-2 py-1.5 font-mono text-fg-muted">{`${a.p95_latency_ms} ms`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>

        <Section title={bi(locale, 'Cola de errores', 'Error tail')} locale={locale}>
          {errors.errors.length === 0 ? (
            <p className="text-xs text-fg-muted">—</p>
          ) : (
            <ul className="space-y-1.5">
              {errors.errors.slice(0, 10).map((e, idx) => (
                <li
                  key={`${e.agent}-${e.occurred_at}-${idx}`}
                  className="flex items-center justify-between rounded-sbs border border-border bg-surface px-2.5 py-1.5 text-2xs"
                >
                  <span className="font-mono text-fg">{e.agent}</span>
                  <span className="text-fg-muted">{e.error_code ?? e.status}</span>
                  <Badge variant={e.status === 'failed' ? 'high' : 'medium'}>{e.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={bi(locale, 'Salud de webhooks', 'Webhook health')} locale={locale}>
          <dl className="space-y-1 text-xs">
            {Object.entries(webhooks.by_status).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between">
                <dt className="text-fg-muted">{k}</dt>
                <dd className="font-mono text-fg">{v}</dd>
              </div>
            ))}
            {webhooks.last_failures.length === 0 ? (
              <p className="text-fg-subtle">{bi(locale, 'Sin fallos recientes.', 'No recent failures.')}</p>
            ) : null}
            <div className="flex items-center justify-between border-t border-border-subtle pt-1">
              <dt className="text-fg-muted">{bi(locale, 'Profundidad de colas', 'Queue depth')}</dt>
              <dd className="font-mono text-fg">
                {Object.values(queues.queues).join(', ') || '—'}
              </dd>
            </div>
          </dl>
        </Section>
      </div>

      <Section title={bi(locale, 'Acciones de remediación', 'Remediation actions')} locale={locale}>
        <ActionBar actions={actions.actions} locale={locale} />
      </Section>
    </div>
  );
}
