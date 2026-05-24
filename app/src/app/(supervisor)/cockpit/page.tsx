import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { CockpitClient } from '@/components/cockpit/CockpitClient';
import { PageHeader } from '@/components/shell/PageHeader';
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
    liveIngestion: {
      title: t(locale, 'live_ingestion.title'),
      subtitle: t(locale, 'live_ingestion.subtitle'),
      preview_disclaimer: t(locale, 'pilot.preview_disclaimer'),
      pilot_badge: t(locale, 'pilot.badge'),
      live_toggle: t(locale, 'live_ingestion.live_toggle'),
      paused_toggle: t(locale, 'live_ingestion.paused_toggle'),
      mtls_label: t(locale, 'live_ingestion.mtls_label'),
      simulate_button: t(locale, 'live_ingestion.simulate_button'),
      simulate_toast_title: t(locale, 'live_ingestion.simulate_toast_title'),
      simulate_toast_body: t(locale, 'live_ingestion.simulate_toast_body'),
      timeline_title: t(locale, 'live_ingestion.timeline_title'),
      diff_title: t(locale, 'live_ingestion.diff_title'),
      diff_tag_before: t(locale, 'live_ingestion.diff_tag_before'),
      diff_tag_after: t(locale, 'live_ingestion.diff_tag_after'),
      diff_before_text: t(locale, 'live_ingestion.diff_before_text'),
      diff_after_text: t(locale, 'live_ingestion.diff_after_text'),
      policy_footer: t(locale, 'live_ingestion.policy_footer'),
      events: {
        received: t(locale, 'live_ingestion.events.received'),
        validated: t(locale, 'live_ingestion.events.validated'),
        redacted: t(locale, 'live_ingestion.events.redacted'),
        persisted: t(locale, 'live_ingestion.events.persisted'),
        broadcast: t(locale, 'live_ingestion.events.broadcast'),
      },
    },
  };

  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={[
          t(locale, 'cockpit.page.breadcrumb_supervision'),
          t(locale, 'cockpit.page.breadcrumb_conduct'),
          t(locale, 'cockpit.page.breadcrumb_current'),
        ]}
        title={t(locale, 'cockpit.page.title')}
        subtitle={t(locale, 'cockpit.page.subtitle')}
        meta={t(locale, 'cockpit.page.meta')}
      />
      <div className="mx-auto w-full max-w-7xl px-6 py-4">
        <CockpitClient initialSnapshot={snapshot} labels={labels} />
      </div>
    </main>
  );
}
