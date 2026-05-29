import { safeGet } from '@/auth/persona-server';
import { AggregationStrip, type Tile } from '@/components/persona/AggregationStrip';
import { InsightChatbotPanel } from '@/components/persona/InsightChatbotPanel';
import { InsightsPanel, type Insight } from '@/components/persona/InsightsPanel';
import { ActionBar, AgentGrid, FindingsTable, Section } from '@/components/persona/primitives';
import { Badge } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { personaTitle, type PersonaConfig } from '@/lib/persona';
import type {
  ActionsResponse,
  AgentsResponse,
  FindingsResponse,
  SuggestedQuestions,
} from '@/types/persona-dashboards';

interface FiBrief {
  brief_id: string;
  institution_id: string;
  motivo_code: string;
  status: string;
  created_at: string;
  response_deadline: string | null;
}
interface FiBriefsResponse {
  items: FiBrief[];
  total: number;
}

export async function SupervisorDashboard({
  persona,
  locale,
}: {
  persona: PersonaConfig;
  locale: Locale;
}) {
  const [briefs, actions, findings, agents, suggested] = await Promise.all([
    safeGet<FiBriefsResponse>(persona, '/v1/internal/fi_briefs', { items: [], total: 0 }),
    safeGet<ActionsResponse>(persona, '/v1/internal/cockpit/actions', { actions: [], total: 0 }),
    safeGet<FindingsResponse>(persona, '/v1/internal/findings', { items: [] }),
    safeGet<AgentsResponse>(persona, '/v1/internal/cockpit/agents?window=24h', {
      agents: [],
      window: '24h',
      computed_at: '',
    }),
    safeGet<SuggestedQuestions>(
      persona,
      '/v1/chatbot/suggested_questions',
      { persona: persona.role, questions: [] },
      { asUser: true },
    ),
  ]);

  const fiAgents = agents.agents.filter((a) => a.is_fi_facing);
  const highCount = findings.items.filter((f) => {
    const s = f.severity.toLowerCase();
    return s === 'high' || s === 'alta';
  }).length;

  const tiles: Tile[] = [
    {
      label: bi(locale, 'Briefs pendientes', 'Briefs awaiting approval'),
      value: briefs.total,
      tone: briefs.total > 0 ? 'amber' : 'green',
    },
    {
      label: bi(locale, 'Patrones', 'Patterns'),
      value: findings.items.length,
      tone: 'neutral',
    },
    {
      label: bi(locale, 'Severidad alta', 'High severity'),
      value: highCount,
      tone: highCount > 0 ? 'red' : 'green',
      trend: highCount > 0 ? 'up' : 'flat',
    },
    {
      label: bi(locale, 'Agentes de cara a IF', 'FI-facing agents'),
      value: fiAgents.length,
      tone: 'neutral',
    },
  ];

  const insights: Insight[] = [
    {
      tone: highCount > 0 ? 'red' : 'green',
      headline: bi(
        locale,
        `${highCount} patrones de severidad alta en las IF asignadas`,
        `${highCount} HIGH-severity patterns across assigned FIs`,
      ),
      body: bi(
        locale,
        'Outliers de riesgo entre pares que pueden requerir un brief a la institución.',
        'Peer-risk outliers that may warrant a brief to the institution.',
      ),
      meta: `${findings.items.length} ${bi(locale, 'patrones', 'patterns')}`,
    },
    {
      tone: briefs.total > 0 ? 'amber' : 'green',
      headline: bi(
        locale,
        `${briefs.total} brief(s) esperando tu firma`,
        `${briefs.total} brief(s) awaiting your sign-off`,
      ),
      body: bi(
        locale,
        'Aprueba o delega los briefs de Reclamito antes del SLA del equipo.',
        'Approve or delegate Reclamito briefs before the team SLA.',
      ),
      meta: `${briefs.total} ${bi(locale, 'pendientes', 'pending')}`,
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
            {bi(locale, 'Panorama de patrones de las IF asignadas', 'Pattern landscape for assigned FIs')}
          </p>
        </header>

        <AggregationStrip tiles={tiles} />

        <InsightsPanel title={bi(locale, 'Insights', 'Insights')} insights={insights} />

        <Section
          title={bi(locale, 'Briefs pendientes de aprobación', 'Briefs awaiting sign-off')}
          locale={locale}
          explainKey="fi_brief_approval_consequence"
        >
          {briefs.items.length === 0 ? (
            <p className="text-xs text-fg-muted">
              {bi(locale, 'No hay briefs pendientes.', 'No briefs awaiting sign-off.')}
            </p>
          ) : (
            <ul className="space-y-2">
              {briefs.items.map((b) => (
                <li
                  key={b.brief_id}
                  className="flex items-center justify-between rounded-sbs border border-border bg-surface p-2.5 text-xs"
                >
                  <div>
                    <span className="font-mono text-fg">{b.institution_id}</span>
                    <span className="ml-2 text-fg-muted">{b.motivo_code}</span>
                  </div>
                  <Badge variant="pending">{b.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={bi(locale, 'Acciones', 'Actions')} locale={locale}>
          <ActionBar actions={actions.actions} locale={locale} />
        </Section>

        <Section
          title={bi(locale, 'Patrones / outliers de riesgo entre pares', 'Patterns / peer-risk outliers')}
          locale={locale}
          explainKey="percentile"
        >
          <FindingsTable rows={findings.items} locale={locale} max={25} />
        </Section>
      </div>

      <div className="space-y-4">
        <Section title={bi(locale, 'Agentes', 'Agents')} locale={locale}>
          <AgentGrid agents={fiAgents} locale={locale} />
        </Section>
        <InsightChatbotPanel
          locale={locale}
          initialSession={null}
          suggestedQuestions={suggested.questions}
        />
      </div>
    </div>
  );
}
