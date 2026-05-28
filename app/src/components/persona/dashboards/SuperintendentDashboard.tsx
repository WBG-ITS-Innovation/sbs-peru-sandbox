import { safeGet } from '@/auth/persona-server';
import { InsightChatbotPanel } from '@/components/persona/InsightChatbotPanel';
import { ActionBar, AgentGrid, Section } from '@/components/persona/primitives';
import { Badge } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { personaTitle, type PersonaConfig } from '@/lib/persona';
import type {
  ActionsResponse,
  AgentsResponse,
  SectorBroadcastSummary,
  SuggestedQuestions,
} from '@/types/persona-dashboards';

interface PatternSummary {
  pattern_id: string;
  pattern_type: string;
  severity_band: string;
  severity_score: number;
  contributing_complaint_count: number;
  summary_es: string;
  summary_en?: string;
}
interface TopPatternsResponse {
  items: PatternSummary[];
}

export async function SuperintendentDashboard({
  persona,
  locale,
}: {
  persona: PersonaConfig;
  locale: Locale;
}) {
  const [digest, broadcasts, actions, agents, suggested] = await Promise.all([
    safeGet<TopPatternsResponse>(persona, '/v1/internal/exec/top_patterns_summary', { items: [] }),
    safeGet<SectorBroadcastSummary>(persona, '/v1/internal/exec/sector_broadcasts', {
      awaiting_co_approval: 0,
      awaiting_my_secondary_approval: 0,
      items: [],
    }),
    safeGet<ActionsResponse>(persona, '/v1/internal/cockpit/actions', { actions: [], total: 0 }),
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

  return (
    <div className="mx-auto grid w-full max-w-screen-2xl grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-4">
        <header>
          <h1 className="text-xl font-semibold tracking-tight text-fg">
            {persona.name} · {personaTitle(persona, locale)}
          </h1>
          <p className="text-xs text-fg-muted">
            {bi(locale, 'Vista ejecutiva · solo agregados', 'Executive view · aggregates only')}
          </p>
        </header>

        <Section
          title={bi(locale, 'Resumen semanal (vista previa)', 'Weekly digest preview')}
          locale={locale}
        >
          {digest.items.length === 0 ? (
            <p className="text-xs text-fg-muted">
              {bi(locale, 'Sin patrones para resumir.', 'No patterns to summarize.')}
            </p>
          ) : (
            <ul className="space-y-2">
              {digest.items.slice(0, 6).map((p) => (
                <li key={p.pattern_id} className="rounded-sbs border border-border bg-surface p-2.5">
                  <div className="mb-1 flex items-center gap-1.5">
                    <Badge variant={p.severity_band === 'HIGH' ? 'high' : 'medium'}>
                      {p.pattern_type}
                    </Badge>
                    <span className="font-mono text-2xs text-fg-subtle">
                      {p.contributing_complaint_count} {bi(locale, 'reclamos', 'complaints')}
                    </span>
                  </div>
                  <p className="text-xs text-fg">{bi(locale, p.summary_es, p.summary_en ?? p.summary_es)}</p>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section
          title={bi(locale, 'Alertas sectoriales para co-aprobación', 'Sector broadcasts awaiting co-approval')}
          locale={locale}
          explainKey="fi_brief_approval_consequence"
          right={
            <Badge variant={broadcasts.awaiting_co_approval > 0 ? 'high' : 'default'}>
              {broadcasts.awaiting_co_approval}
            </Badge>
          }
        >
          {broadcasts.items.length === 0 ? (
            <p className="text-xs text-fg-muted">
              {bi(locale, 'Ninguna pendiente.', 'None pending.')}
            </p>
          ) : (
            <ul className="space-y-2">
              {broadcasts.items.map((b) => (
                <li
                  key={b.broadcast_id}
                  className="flex items-center justify-between gap-2 rounded-sbs border border-border bg-surface p-2.5 text-xs"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <Badge variant={b.urgency === 'CRITICAL' ? 'critical' : 'medium'}>
                        {b.urgency}
                      </Badge>
                      <span className="text-fg-muted">
                        {b.target_fi_count} {bi(locale, 'IF objetivo', 'target FIs')}
                      </span>
                    </div>
                    <div className="mt-0.5 truncate font-mono text-2xs text-fg-subtle">
                      {b.threat_indicators.join(' · ')}
                    </div>
                  </div>
                  <Badge variant="pending">{b.status}</Badge>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3">
            <ActionBar actions={actions.actions} locale={locale} />
          </div>
        </Section>

        <Section
          title={bi(locale, 'Agentes de cara a las IF (agregado)', 'FI-facing agents (aggregate)')}
          locale={locale}
        >
          <AgentGrid agents={agents.agents} locale={locale} />
        </Section>
      </div>

      <div className="space-y-4">
        <InsightChatbotPanel
          locale={locale}
          initialSession={null}
          suggestedQuestions={suggested.questions}
        />
      </div>
    </div>
  );
}
