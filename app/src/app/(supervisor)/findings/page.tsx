import { Inbox } from 'lucide-react';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';
import { EmptyState } from '@/components/ui';
import { FindingsFilters } from '@/components/findings/FindingsFilters';
import { FindingsTable } from '@/components/findings/FindingsTable';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';
import { internalGet } from '@/lib/api';
import type { FindingsListResponse } from '@/types/findings';

export const dynamic = 'force-dynamic';

interface FindingsPageProps {
  searchParams: Record<string, string | string[] | undefined>;
}

function asString(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}

export default async function FindingsListPage({ searchParams }: FindingsPageProps) {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const persona = activePersona(session);
  const locale = currentLocale();

  // Forward filter query params straight through to the API. The
  // server-side defaults apply when nothing is set.
  const query = new URLSearchParams();
  for (const key of [
    'institution',
    'severity',
    'source',
    'classification',
    'confidence_band',
    'from_received_at',
    'to_received_at',
    'use_defaults',
  ]) {
    const v = asString(searchParams[key]);
    if (v) query.set(key, v);
  }

  const response = await internalGet<FindingsListResponse>(
    `/v1/internal/findings?${query.toString()}`,
    { roles: persona.roles },
  );

  const tableLabels = {
    columns: {
      complaint_id: t(locale, 'findings.columns.complaint_id'),
      institution: t(locale, 'findings.columns.institution'),
      classification: t(locale, 'findings.columns.classification'),
      confidence: t(locale, 'findings.columns.confidence'),
      severity: t(locale, 'findings.columns.severity'),
      source: t(locale, 'findings.columns.source'),
      drafted_by_agent: t(locale, 'findings.columns.drafted_by_agent'),
      received_at: t(locale, 'findings.columns.received_at'),
    },
    source: {
      tier1: t(locale, 'findings.filters.source_tier1'),
      tier2: t(locale, 'findings.filters.source_tier2'),
    },
    drafted: t(locale, 'findings.columns.drafted_by_agent'),
  };

  const filterLabels = {
    label: t(locale, 'findings.filters.label'),
    institution: t(locale, 'findings.filters.institution'),
    severity: t(locale, 'findings.filters.severity'),
    source: t(locale, 'findings.filters.source'),
    confidence_band: t(locale, 'findings.filters.confidence_band'),
    any: t(locale, 'findings.filters.any'),
    apply: t(locale, 'findings.filters.apply'),
    reset: t(locale, 'findings.filters.reset'),
    source_tier1: t(locale, 'findings.filters.source_tier1'),
    source_tier2: t(locale, 'findings.filters.source_tier2'),
    band_low: t(locale, 'findings.filters.band_low'),
    band_medium: t(locale, 'findings.filters.band_medium'),
    band_high: t(locale, 'findings.filters.band_high'),
  };

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold text-fg">{t(locale, 'findings.title')}</h1>
        <p className="text-sm text-fg-muted">{t(locale, 'findings.subtitle')}</p>
      </header>

      <FindingsFilters labels={filterLabels} />

      {response.items.length === 0 ? (
        <EmptyState
          icon={<Inbox className="h-6 w-6" aria-hidden="true" />}
          title={t(locale, 'findings.empty.title')}
          body={t(locale, 'findings.empty.body')}
          primaryAction={{
            label: t(locale, 'findings.empty.primary'),
            href: '/findings',
          }}
        />
      ) : (
        <FindingsTable items={response.items} locale={locale} labels={tableLabels} />
      )}
    </main>
  );
}
