import { History } from 'lucide-react';
import Link from 'next/link';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';
import { AuditFilters } from '@/components/audit/AuditFilters';
import { AuditTable } from '@/components/audit/AuditTable';
import { Button, EmptyState } from '@/components/ui';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';
import { internalGet } from '@/lib/api';
import type { AuditResponse } from '@/types/audit';

export const dynamic = 'force-dynamic';

const PAGE_SIZE = 50;

function asString(v: string | string[] | undefined): string | undefined {
  if (Array.isArray(v)) return v[0];
  return v;
}

export default async function AuditPage({
  searchParams,
}: {
  searchParams: Record<string, string | string[] | undefined>;
}) {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const persona = activePersona(session);
  const locale = currentLocale();

  const page = Math.max(1, Number(asString(searchParams.page) ?? '1') || 1);
  const params = new URLSearchParams();
  params.set('page', String(page));
  params.set('page_size', String(PAGE_SIZE));
  for (const key of [
    'actor_type',
    'actor_id',
    'action',
    'object_type',
    'object_id',
    'from_created_at',
    'to_created_at',
  ]) {
    const v = asString(searchParams[key]);
    if (v) params.set(key, v);
  }

  const response = await internalGet<AuditResponse>(
    `/v1/internal/audit?${params.toString()}`,
    { roles: persona.roles },
  );

  const pageLabel = t(locale, 'audit.pagination.page_of')
    .replace('{page}', String(response.page))
    .replace('{total}', String(Math.max(1, response.total_pages)));

  function pageHref(target: number): string {
    const next = new URLSearchParams(params);
    next.set('page', String(target));
    return `/audit?${next.toString()}`;
  }

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-fg">{t(locale, 'audit.title')}</h1>
        <p className="text-sm text-fg-muted">{t(locale, 'audit.subtitle')}</p>
      </header>

      <AuditFilters
        labels={{
          label: t(locale, 'audit.filters.label'),
          actor: t(locale, 'audit.filters.actor'),
          action: t(locale, 'audit.filters.action'),
          object_type: t(locale, 'audit.filters.object_type'),
          object_id: t(locale, 'audit.filters.object_id'),
          apply: t(locale, 'audit.filters.apply'),
          reset: t(locale, 'audit.filters.reset'),
        }}
      />

      {response.items.length === 0 ? (
        <EmptyState
          icon={<History className="h-6 w-6" aria-hidden="true" />}
          title={t(locale, 'audit.empty.title')}
          body={t(locale, 'audit.empty.body')}
          primaryAction={{
            label: t(locale, 'audit.empty.primary'),
            href: '/audit',
          }}
        />
      ) : (
        <>
          <AuditTable
            rows={response.items}
            locale={locale}
            labels={{
              columns: {
                created_at: t(locale, 'audit.columns.created_at'),
                actor: t(locale, 'audit.columns.actor'),
                action: t(locale, 'audit.columns.action'),
                object: t(locale, 'audit.columns.object'),
                details: t(locale, 'audit.columns.details'),
              },
              actor_type_user: t(locale, 'audit.actor_type_user'),
              actor_type_agent: t(locale, 'audit.actor_type_agent'),
              details_label: t(locale, 'audit.details_label'),
            }}
          />
          <nav
            aria-label={t(locale, 'audit.pagination.page_of')}
            className="flex items-center justify-between gap-2 text-xs text-fg-muted"
          >
            <span className="tabular">{pageLabel}</span>
            <div className="flex gap-2">
              {response.page > 1 ? (
                <Button asChild variant="outline" size="sm">
                  <Link href={pageHref(response.page - 1)}>
                    {t(locale, 'audit.pagination.prev')}
                  </Link>
                </Button>
              ) : null}
              {response.page < response.total_pages ? (
                <Button asChild variant="outline" size="sm">
                  <Link href={pageHref(response.page + 1)}>
                    {t(locale, 'audit.pagination.next')}
                  </Link>
                </Button>
              ) : null}
            </div>
          </nav>
        </>
      )}
    </main>
  );
}
