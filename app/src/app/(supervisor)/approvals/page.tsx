import { Inbox, Lock } from 'lucide-react';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { ROLE_ANALYST, ROLE_HEAD } from '@/auth/landing';
import { activePersona, getSession } from '@/auth/session';
import { ApprovalKpisStrip } from '@/components/approvals/ApprovalKpis';
import { ApprovalsTable } from '@/components/approvals/ApprovalsTable';
import { EmptyState } from '@/components/ui';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';
import { internalGet } from '@/lib/api';
import type { ApprovalsQueueResponse } from '@/types/approvals';

export const dynamic = 'force-dynamic';

// Roles permitted to read the approvals queue, mirroring the backend
// dependency `_HEAD_OR_ANALYST` on api/sbs_api/routes/approvals.py.
// ADR 0040 §D7 — supervisor (the Conduct Supervisor) is intentionally excluded; she
// hands off to head (the Conduct Unit Head) or analyst (the Conduct Analyst) via the persona
// switcher in the top bar.
const QUEUE_ROLES = new Set<string>([ROLE_ANALYST, ROLE_HEAD]);

function canReadApprovalsQueue(roles: readonly string[]): boolean {
  return roles.some(role => QUEUE_ROLES.has(role));
}

export default async function ApprovalsQueuePage() {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const persona = activePersona(session);
  const locale = currentLocale();

  // Role check before the upstream call so the supervisor persona
  // does not trip the FastAPI 403 and bubble it up as a Next runtime
  // overlay. Renders the access-controlled state instead — the
  // persona switcher in the top bar is the documented next step.
  if (!canReadApprovalsQueue(persona.roles)) {
    return (
      <main className="mx-auto max-w-7xl space-y-4 p-6">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold text-fg">
            {t(locale, 'approvals.title')}
          </h1>
          <p className="text-sm text-fg-muted">
            {t(locale, 'approvals.subtitle')}
          </p>
        </header>
        <EmptyState
          icon={<Lock className="h-6 w-6" aria-hidden="true" />}
          title={t(locale, 'approvals.access_denied.title')}
          body={t(locale, 'approvals.access_denied.body')}
          primaryAction={{
            label: t(locale, 'approvals.access_denied.primary'),
            href: '/findings',
          }}
        />
      </main>
    );
  }

  const queue = await internalGet<ApprovalsQueueResponse>(
    '/v1/internal/approvals',
    { roles: persona.roles },
  );

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-fg">
          {t(locale, 'approvals.title')}
        </h1>
        <p className="text-sm text-fg-muted">{t(locale, 'approvals.subtitle')}</p>
      </header>

      <ApprovalKpisStrip
        kpis={queue.kpis}
        locale={locale}
        labels={{
          pending: t(locale, 'approvals.kpis.pending'),
          approved_today: t(locale, 'approvals.kpis.approved_today'),
          rejected_today: t(locale, 'approvals.kpis.rejected_today'),
          median_ttd: t(locale, 'approvals.kpis.median_ttd'),
        }}
      />

      {queue.items.length === 0 ? (
        <EmptyState
          icon={<Inbox className="h-6 w-6" aria-hidden="true" />}
          title={t(locale, 'approvals.empty.title')}
          body={t(locale, 'approvals.empty.body')}
          primaryAction={{
            label: t(locale, 'approvals.empty.primary'),
            href: '/queue',
          }}
        />
      ) : (
        <ApprovalsTable
          items={queue.items}
          locale={locale}
          labels={{
            complaint_id: t(locale, 'approvals.columns.complaint_id'),
            institution: t(locale, 'approvals.columns.institution'),
            severity: t(locale, 'approvals.columns.severity'),
            time_pending: t(locale, 'approvals.columns.time_pending'),
            created_by: t(locale, 'approvals.columns.created_by'),
          }}
        />
      )}
    </main>
  );
}
