import { safeGet } from '@/auth/persona-server';
import { InsightChatbotPanel } from '@/components/persona/InsightChatbotPanel';
import {
  ActionBar,
  AgentGrid,
  FindingsTable,
  KpiTile,
  Section,
} from '@/components/persona/primitives';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { personaTitle, type PersonaConfig } from '@/lib/persona';
import type {
  ActionsResponse,
  AgentsResponse,
  ChatSession,
  FindingsResponse,
  SuggestedQuestions,
} from '@/types/persona-dashboards';

const SEEDED_JORGE_SESSION = 'demo-jorge-fraud-chatbot';

export async function UnitHeadDashboard({
  persona,
  locale,
}: {
  persona: PersonaConfig;
  locale: Locale;
}) {
  const [findings, actions, agents, session, suggested] = await Promise.all([
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
  ]);

  const counts = { high: 0, medium: 0, low: 0 };
  for (const f of findings.items) {
    const s = f.severity.toLowerCase();
    if (s === 'high' || s === 'alta') counts.high += 1;
    else if (s === 'medium' || s === 'media') counts.medium += 1;
    else if (s === 'low' || s === 'baja') counts.low += 1;
  }

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

        <Section title={bi(locale, 'Acciones', 'Actions')} locale={locale}>
          <ActionBar actions={actions.actions} locale={locale} />
        </Section>

        <Section
          title={bi(locale, 'Monitoreo de agentes (los 6)', 'Agent monitoring (all 6)')}
          locale={locale}
        >
          <AgentGrid agents={agents.agents} locale={locale} />
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
