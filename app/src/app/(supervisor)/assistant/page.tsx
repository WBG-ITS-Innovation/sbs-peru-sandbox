import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { Sparkles, User } from 'lucide-react';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { LiveAssistantChat } from '@/components/assistant/LiveAssistantChat';
import { Badge } from '@/components/ui/Badge';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { PageHeader } from '@/components/shell/PageHeader';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// /app/assistant — supervisor pilot preview. The expanded view of the
// AI assistant. This page is intentionally inert: the input is disabled
// and no LLM provider is wired in. The disclaimer makes that explicit
// to anyone reviewing. The three static exchanges below illustrate the
// patterns the real assistant will support — they are not live calls.

export const dynamic = 'force-dynamic';

export default function AssistantPage() {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }

  const locale = currentLocale();
  const tr = (key: string) => t(locale, key);

  const pilotBadge = tr('pilot.badge');
  const previewOnly = tr('assistant.preview_only');
  const inputPlaceholder = tr('assistant.input_placeholder');
  const send = tr('assistant.send');
  const beta = tr('assistant.beta');
  const userLabel = tr('assistant.exchanges.user_label');
  const botLabel = tr('assistant.exchanges.bot_label');

  const exchanges = [
    {
      q: tr('assistant.exchanges.anomaly_q'),
      a: tr('assistant.exchanges.anomaly_a'),
      ts: '09:42 PET',
    },
    {
      q: tr('assistant.exchanges.draft_q'),
      a: tr('assistant.exchanges.draft_a'),
      draftFoot: tr('assistant.exchanges.draft_disclaimer'),
      ts: '09:43 PET · 2.1 s',
    },
    {
      q: tr('assistant.exchanges.fee_q'),
      a: tr('assistant.exchanges.fee_a'),
      ts: '09:44 PET',
    },
  ];

  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={['Supervisión', 'Asistente']}
        title={tr('assistant.title')}
        subtitle={tr('assistant.subtitle')}
        right={
          <div className="flex items-center gap-2">
            <Badge variant="role" className="border-brand-gold/40 bg-brand-gold/10 text-brand-navy">
              {beta}
            </Badge>
            <Badge variant="role" className="border-brand-gold/40 bg-brand-gold/10 text-brand-navy">
              {pilotBadge}
            </Badge>
          </div>
        }
      />

      <div className="mx-auto grid w-full max-w-7xl gap-3 px-6 py-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          <Card className="border-border">
            <CardBody className="space-y-4 px-4 py-4">
              {exchanges.map((ex, i) => (
                <div key={i} className="space-y-2">
                  <div className="rounded-sbs border border-border-subtle bg-surface px-3 py-2">
                    <p className="flex items-center gap-1.5 font-mono text-2xs uppercase tracking-wider text-fg-muted">
                      <User className="h-3 w-3" aria-hidden="true" />
                      {userLabel}
                    </p>
                    <p className="mt-1 text-sm text-fg">{ex.q}</p>
                  </div>
                  <div className="rounded-sbs border border-brand-cyan/30 bg-brand-cyan/5 px-3 py-2">
                    <p className="flex items-center gap-1.5 font-mono text-2xs uppercase tracking-wider text-brand-navy">
                      <Sparkles className="h-3 w-3 text-brand-gold" aria-hidden="true" />
                      {botLabel} · <span className="text-fg-muted">{ex.ts}</span>
                    </p>
                    <p className="mt-1 text-sm leading-snug text-fg">{ex.a}</p>
                    {ex.draftFoot ? (
                      <p className="mt-2 rounded-sbs border border-severity-medium-border bg-severity-medium-bg px-2 py-1.5 font-mono text-2xs text-severity-medium-fg">
                        {ex.draftFoot}
                      </p>
                    ) : null}
                  </div>
                </div>
              ))}
            </CardBody>
          </Card>

          <LiveAssistantChat
            csrfToken={session.csrfToken}
            labels={{
              placeholder: inputPlaceholder,
              send,
              thinking: tr('assistant.exchanges.bot_label') + '…',
              user_label: userLabel,
              bot_label: botLabel,
              demo_mode: 'Modo demo · sin API key',
              powered_by: 'Azure OpenAI',
            }}
          />
        </div>

        <aside className="space-y-3">
          <Card className="border-border">
            <CardHeader className="border-b border-border px-4 py-2.5">
              <CardTitle className="font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
                {tr('assistant.suggestions_title')}
              </CardTitle>
            </CardHeader>
            <CardBody className="px-4 py-3">
              <ul className="space-y-2 text-xs">
                <li className="rounded-sbs border border-border-subtle bg-surface px-3 py-2 text-fg">
                  → {tr('assistant.suggestions.compare_months')}
                </li>
                <li className="rounded-sbs border border-border-subtle bg-surface px-3 py-2 text-fg">
                  → {tr('assistant.suggestions.explain_anomaly')}
                </li>
                <li className="rounded-sbs border border-border-subtle bg-surface px-3 py-2 text-fg">
                  → {tr('assistant.suggestions.free_text')}
                </li>
              </ul>
              <p className="mt-3 text-2xs text-fg-muted">{previewOnly}</p>
            </CardBody>
          </Card>

          <Card className="border-border">
            <CardHeader className="border-b border-border px-4 py-2.5">
              <CardTitle className="font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
                {tr('assistant.model_label')}
              </CardTitle>
            </CardHeader>
            <CardBody className="px-4 py-3">
              <p className="font-mono text-xs text-fg">AZURE_OPENAI_DEPLOYMENT</p>
              <p className="mt-1 text-2xs text-fg-muted">{previewOnly}</p>
            </CardBody>
          </Card>
        </aside>
      </div>
    </main>
  );
}
