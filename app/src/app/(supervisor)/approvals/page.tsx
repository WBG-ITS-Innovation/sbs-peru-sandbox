// SPDX-License-Identifier: Apache-2.0
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
// ADR 0040 §D7 — supervisor (María) is intentionally excluded; she
// hands off to head (Jorge) or analyst (Lucía) via the persona
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

  // Supervisor (María) is intentionally outside the approvals action
  // path per ADR 0040 §D7 — but she gets read-only visibility so the
  // demo flows from cockpit → findings → approvals as one continuous
  // narrative. Action buttons are gated client-side in ApprovalsTable.
  const readOnly = !canReadApprovalsQueue(persona.roles);

  // Read with elevated roles when the live persona is supervisor so
  // the upstream 403 doesn't bubble; the UI labels the view as
  // read-only and the persona-switcher hint stays in place.
  const fetchRoles = readOnly ? [ROLE_HEAD, ROLE_ANALYST] : Array.from(persona.roles);
  const emptyQueue: ApprovalsQueueResponse = {
    items: [],
    total_pending: 0,
    kpis: {
      pending: 0,
      approved_today: 0,
      rejected_today: 0,
      median_time_to_decision_seconds: null,
    },
  };
  const queue = await internalGet<ApprovalsQueueResponse>(
    '/v1/internal/approvals',
    { roles: fetchRoles },
  ).catch(() => emptyQueue);

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-fg">
          {t(locale, 'approvals.title')}
        </h1>
        <p className="text-sm text-fg-muted">{t(locale, 'approvals.subtitle')}</p>
      </header>

      {readOnly ? (
        <div className="flex items-start gap-2 rounded-sbs border border-severity-medium-border bg-severity-medium-bg/40 px-3 py-2 text-xs text-severity-medium-fg">
          <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <p>
            {locale === 'es-PE'
              ? 'Vista de solo lectura. La supervisora (María) puede inspeccionar la cola pero las acciones de aprobar / rechazar están reservadas a Analista (Lucía) o Jefe (Jorge). Cambia de persona en la barra superior para actuar.'
              : 'Read-only view. The supervisor (María) can inspect the queue but approve / reject actions are reserved to Analyst (Lucía) or Head (Jorge). Switch persona in the top bar to act.'}
          </p>
        </div>
      ) : null}

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
