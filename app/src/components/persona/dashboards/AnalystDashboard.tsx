import { safeGet } from '@/auth/persona-server';
import { AggregationStrip, type Tile } from '@/components/persona/AggregationStrip';
import { InsightChatbotPanel } from '@/components/persona/InsightChatbotPanel';
import { InsightsPanel, type Insight } from '@/components/persona/InsightsPanel';
import { ActionBar, AgentGrid, FindingsTable, Section } from '@/components/persona/primitives';
import { TaskInbox, TaskOutbox } from '@/components/persona/TaskQueues';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { personaTitle, type PersonaConfig } from '@/lib/persona';
import type {
  ActionsResponse,
  AgentsResponse,
  FindingsResponse,
  SuggestedQuestions,
  TasksResponse,
} from '@/types/persona-dashboards';

export async function AnalystDashboard({
  persona,
  locale,
}: {
  persona: PersonaConfig;
  locale: Locale;
}) {
  const [findings, actions, inbox, outbox, agents, suggested] = await Promise.all([
    safeGet<FindingsResponse>(persona, '/v1/internal/findings', { items: [] }),
    safeGet<ActionsResponse>(persona, '/v1/internal/cockpit/actions', { actions: [], total: 0 }),
    safeGet<TasksResponse>(
      persona,
      `/v1/internal/cockpit/tasks/inbox?user_id=${persona.taskUserId}`,
      { items: [], total: 0 },
    ),
    safeGet<TasksResponse>(
      persona,
      `/v1/internal/cockpit/tasks/outbox?user_id=${persona.taskUserId}`,
      { items: [], total: 0 },
    ),
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
  const bancoHigh = findings.items.filter(
    (f) =>
      (f.severity.toLowerCase() === 'high' || f.severity.toLowerCase() === 'alta') &&
      f.institution_name.toUpperCase().includes('BANCO'),
  ).length;

  const tiles: Tile[] = [
    {
      label: bi(locale, 'Reclamos', 'Complaints'),
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
      label: bi(locale, 'Tareas pendientes', 'Pending tasks'),
      value: inbox.total,
      tone: inbox.total > 0 ? 'amber' : 'green',
    },
    {
      label: bi(locale, 'Acciones disponibles', 'Available actions'),
      value: actions.total,
      tone: 'neutral',
    },
  ];

  const insights: Insight[] = [
    {
      tone: bancoHigh > 0 ? 'red' : 'neutral',
      headline: bi(
        locale,
        `${bancoHigh} reclamos de severidad alta de BANCO_DEMO_001`,
        `${bancoHigh} HIGH-severity complaints from BANCO_DEMO_001`,
      ),
      body: bi(
        locale,
        'Agrupación posible de reclamos no detectada por el análisis automático. Considera proponer un patrón.',
        'A possible cluster the automatic analysis did not group. Consider proposing a pattern.',
      ),
      meta: `${findings.items.length} ${bi(locale, 'reclamos', 'complaints')} · ${highCount} ${bi(locale, 'altos', 'high')}`,
    },
    {
      tone: inbox.total > 0 ? 'amber' : 'green',
      headline: bi(
        locale,
        `${inbox.total} tarea(s) en tu bandeja de entrada`,
        `${inbox.total} task(s) in your inbox`,
      ),
      body: bi(
        locale,
        'Tareas delegadas que esperan tu confirmación o rechazo.',
        'Delegated tasks awaiting your acknowledgement or decline.',
      ),
      meta: `${inbox.total} ${bi(locale, 'pendientes', 'pending')}`,
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
            {bi(locale, 'Inspección de reclamos individuales', 'Individual complaint inspection')}
          </p>
        </header>

        <AggregationStrip tiles={tiles} />

        <InsightsPanel title={bi(locale, 'Insights', 'Insights')} insights={insights} />

        <Section
          title={bi(locale, 'Cola de reclamos asignados', 'Assigned complaint queue')}
          locale={locale}
        >
          <FindingsTable rows={findings.items} locale={locale} max={50} />
        </Section>

        <Section title={bi(locale, 'Acciones', 'Actions')} locale={locale}>
          <ActionBar actions={actions.actions} locale={locale} />
        </Section>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Section title={bi(locale, 'Bandeja de entrada', 'Task inbox')} locale={locale}>
            <TaskInbox tasks={inbox.items} locale={locale} />
          </Section>
          <Section title={bi(locale, 'Bandeja de salida', 'Task outbox')} locale={locale}>
            <TaskOutbox tasks={outbox.items} locale={locale} />
          </Section>
        </div>
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
