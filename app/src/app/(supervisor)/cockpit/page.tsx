import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { CockpitClient } from '@/components/cockpit/CockpitClient';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';
import { internalGet } from '@/lib/api';
import type { CockpitSnapshot } from '@/types/cockpit';

// Server component: fetches the snapshot via Next.js → FastAPI server-
// to-server, then hands it to the client wrapper. The client opens an
// EventSource to /app/api/sse/cockpit and merges deltas with the
// snapshot state.
//
// Unauthenticated → /app/login. The route doesn't render the cockpit
// for a caller without a session.

export const dynamic = 'force-dynamic';

export default async function CockpitPage() {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }

  const snapshot = await internalGet<CockpitSnapshot>('/v1/internal/cockpit');
  const locale = currentLocale();

  const labels = {
    locale,
    kpis: {
      complaints_24h: t(locale, 'cockpit.kpis.complaints_24h'),
      anomalies_active: t(locale, 'cockpit.kpis.anomalies_active'),
      top_institutions: t(locale, 'cockpit.kpis.top_institutions'),
    },
    crossSource: {
      title: t(locale, 'cockpit.cross_source.title'),
      illustrative: t(locale, 'cockpit.cross_source.illustrative'),
      channels: {
        complaints: t(locale, 'cockpit.cross_source.channels.complaints'),
        social: t(locale, 'cockpit.cross_source.channels.social'),
        indecopi: t(locale, 'cockpit.cross_source.channels.indecopi'),
        plavia: t(locale, 'cockpit.cross_source.channels.plavia'),
        internal: t(locale, 'cockpit.cross_source.channels.internal'),
      },
    },
    anomaly: {
      threshold: t(locale, 'cockpit.anomaly.threshold'),
      composite: t(locale, 'cockpit.anomaly.composite'),
      why_fired: t(locale, 'cockpit.anomaly.why_fired'),
      channels: t(locale, 'cockpit.anomaly.channels'),
      open_findings: t(locale, 'cockpit.anomaly.open_findings'),
    },
    emptyTier1: {
      title: t(locale, 'cockpit.tier1_empty.title'),
      body: t(locale, 'cockpit.tier1_empty.body'),
      primary: {
        label: t(locale, 'cockpit.tier1_empty.primary'),
        href: '/findings',
      },
    },
    emptyTier2: {
      title: t(locale, 'cockpit.tier2_empty.title'),
      body: t(locale, 'cockpit.tier2_empty.body'),
      primary: {
        label: t(locale, 'cockpit.tier2_empty.primary'),
        href: '/findings',
      },
    },
    emptyAnomalies: {
      title: t(locale, 'cockpit.anomalies_empty.title'),
      body: t(locale, 'cockpit.anomalies_empty.body'),
    },
  };

  return (
    <main className="mx-auto max-w-7xl space-y-4 p-6">
      <CockpitClient initialSnapshot={snapshot} labels={labels} />
    </main>
  );
}
