import { safeGet } from '@/auth/persona-server';
import { ActionButton } from '@/components/persona/ActionButton';
import { AggregationStrip, type Tile } from '@/components/persona/AggregationStrip';
import { InsightChatbotPanel } from '@/components/persona/InsightChatbotPanel';
import { InsightsPanel, type Insight } from '@/components/persona/InsightsPanel';
import {
  ActionBar,
  AgentGrid,
  FindingsTable,
  KpiTile,
  Section,
} from '@/components/persona/primitives';
import type { Locale } from '@/i18n';
import { internalGet } from '@/lib/api';
import { bi } from '@/lib/bi';
import { personaTitle, type PersonaConfig } from '@/lib/persona';
import type {
  ActionDef,
  ActionsResponse,
  AgentsResponse,
  ChatSession,
  FindingsResponse,
  SectorBroadcastSummary,
  SuggestedQuestions,
} from '@/types/persona-dashboards';

const SEEDED_JORGE_SESSION = 'demo-jorge-fraud-chatbot';

// Jorge is the legitimate PRIMARY approver of sector broadcasts, but the
// exec list endpoint is scoped to the Superintendent. For the demo we
// surface (read-only) the pending broadcast he is entitled to approve.
async function fetchPendingBroadcast(): Promise<SectorBroadcastSummary | null> {
  try {
    return await internalGet<SectorBroadcastSummary>(
      '/v1/internal/exec/sector_broadcasts',
      { roles: ['sbs:superintendent'] },
    );
  } catch {
    return null;
  }
}

export async function UnitHeadDashboard({
  persona,
  locale,
}: {
  persona: PersonaConfig;
  locale: Locale;
}) {
  const [findings, actions, agents, session, suggested, broadcasts] = await Promise.all([
    safeGet<FindingsResponse>(persona, '/v1/internal/findings', { items: [] }),
    safeGet<ActionsResponse>(persona, '/v1/internal/cockpit/actions', { actions: [], total: 0 }),
    safeGet<AgentsResponse>(persona, '/v1/internal/cockpit/agents?window=24h', {
      agents: [],
      window: '24h',
      computed_at: '',
    }),
    safeGet<ChatSession | null>(
      persona,
      `/v1/chatbot/sessions/${SEEDED_JORGE_SESSION}`,
      null,
      { asUser: true },
    ),
    safeGet<SuggestedQuestions>(
      persona,
      '/v1/chatbot/suggested_questions',
      { persona: persona.role, questions: [] },
      { asUser: true },
    ),
    fetchPendingBroadcast(),
  ]);

  const counts = { high: 0, medium: 0, low: 0 };
  for (const f of findings.items) {
    const s = f.severity.toLowerCase();
    if (s === 'high' || s === 'alta') counts.high += 1;
    else if (s === 'medium' || s === 'media') counts.medium += 1;
    else if (s === 'low' || s === 'baja') counts.low += 1;
  }

  const pending = broadcasts?.items.find((b) => b.status === 'AWAITING_DUAL_APPROVAL') ?? null;
  const primaryAction = actions.actions.find(
    (a) => a.action_id === 'approve_sector_broadcast_primary',
  );

  const tiles: Tile[] = [
    {
      label: bi(locale, 'Patrones severidad alta', 'HIGH severity patterns'),
      value: counts.high,
      tone: counts.high > 0 ? 'red' : 'green',
      trend: counts.high > 0 ? 'up' : 'flat',
    },
    {
      label: bi(locale, 'Broadcasts pendientes', 'Sector broadcasts pending'),
      value: broadcasts?.awaiting_co_approval ?? 0,
      tone: (broadcasts?.awaiting_co_approval ?? 0) > 0 ? 'amber' : 'green',
    },
    {
      label: bi(locale, 'Patrones totales', 'Patterns total'),
      value: findings.items.length,
      tone: 'neutral',
    },
    {
      label: bi(locale, 'Agentes monitoreados', 'Agents monitored'),
      value: agents.agents.length,
      tone: 'neutral',
    },
  ];

  const approveButton =
    pending && primaryAction ? (
      <ActionButton
        action={primaryAction}
        locale={locale}
        presetTargetId={pending.broadcast_id}
        presetLabel={bi(locale, 'Aprobar (primario)', 'Approve (primary)')}
      />
    ) : undefined;

  const insights: Insight[] = [
    {
      tone: 'red',
      headline: bi(
        locale,
        'Señales de FRAUD_EMERGENCE al alza — Lupaman preparó una alerta sectorial',
        'FRAUD_EMERGENCE signals rising — Lupaman drafted a sector broadcast',
      ),
      body: bi(
        locale,
        'BANCO_DEMO_001 muestra una emergencia de fraude (severidad ALTA) por señales de redes sociales, reclamos e INDECOPI. La alerta sectorial está pendiente de tu aprobación primaria.',
        'BANCO_DEMO_001 shows a HIGH-severity fraud emergence across social, complaints and INDECOPI signals. The sector broadcast awaits your primary approval.',
      ),
      meta: pending
        ? `broadcast ${pending.broadcast_id.slice(0, 8)} · ${pending.target_fi_count} ${bi(locale, 'IF objetivo', 'target FIs')}`
        : bi(locale, 'Sin broadcast pendiente', 'No pending broadcast'),
      action: approveButton,
    },
    {
      tone: counts.high > 0 ? 'amber' : 'green',
      headline: bi(
        locale,
        `${counts.high} patrones de severidad alta en el panorama`,
        `${counts.high} HIGH-severity patterns in the landscape`,
      ),
      body: bi(
        locale,
        'Revisa el panorama de patrones abajo; los de severidad alta requieren decisión de la unidad.',
        'Review the pattern landscape below; HIGH-severity patterns require a unit decision.',
      ),
      meta: `${findings.items.length} ${bi(locale, 'patrones', 'patterns')}`,
    },
  ];

  return (
    <div className="mx-auto grid w-full max-w-screen-2xl grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <header>
          <h1 className="text-xl font-semibold tracking-tight text-fg">
            {persona.name} · {personaTitle(persona, locale)}
          </h1>
          <p className="text-xs text-fg-muted">
            {bi(locale, 'Panorama completo de patrones · autoridad final', 'Full pattern landscape · final authority')}
          </p>
        </header>

        <AggregationStrip tiles={tiles} />

        <Section
          title={bi(locale, 'Monitoreo de agentes (los 6)', 'Agent monitoring (all 6)')}
          locale={locale}
        >
          <AgentGrid agents={agents.agents} locale={locale} />
        </Section>

        <InsightsPanel title={bi(locale, 'Insights', 'Insights')} insights={insights} />

        <Section
          title={bi(locale, 'Panorama de patrones', 'Pattern landscape')}
          locale={locale}
          explainKey="severity_band"
        >
          <div className="mb-3 grid grid-cols-3 gap-2">
            <KpiTile label={bi(locale, 'Alta', 'High')} value={counts.high} locale={locale} />
            <KpiTile label={bi(locale, 'Media', 'Medium')} value={counts.medium} locale={locale} />
            <KpiTile label={bi(locale, 'Baja', 'Low')} value={counts.low} locale={locale} />
          </div>
          <FindingsTable rows={findings.items} locale={locale} max={50} />
        </Section>

        <Section
          title={bi(locale, 'Aprobaciones', 'Approvals')}
          locale={locale}
          explainKey="fi_brief_approval_consequence"
        >
          {pending ? (
            <div className="flex items-center justify-between gap-2 rounded-sbs border border-border bg-surface p-2.5 text-xs">
              <div className="min-w-0">
                <div className="font-mono text-fg">{pending.broadcast_id.slice(0, 8)}</div>
                <div className="text-fg-muted">
                  {pending.urgency} · {pending.target_fi_count}{' '}
                  {bi(locale, 'IF objetivo', 'target FIs')} · {pending.status}
                </div>
              </div>
              {approveButton}
            </div>
          ) : (
            <p className="text-xs text-fg-muted">
              {bi(locale, 'No hay broadcasts pendientes de aprobación primaria.', 'No broadcasts awaiting primary approval.')}
            </p>
          )}
        </Section>

        <Section title={bi(locale, 'Acciones', 'Actions')} locale={locale}>
          <ActionBar actions={actions.actions} locale={locale} />
        </Section>
      </div>

      <div className="space-y-4">
        <InsightChatbotPanel
          locale={locale}
          initialSession={session}
          suggestedQuestions={suggested.questions}
        />
      </div>
    </div>
  );
}
