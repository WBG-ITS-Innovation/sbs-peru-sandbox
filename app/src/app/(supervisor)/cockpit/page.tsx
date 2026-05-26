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
      sandbox_badge: t(locale, 'live_ingestion.sandbox_badge'),
      nrt_label: t(locale, 'live_ingestion.nrt_label'),
      submit_button: t(locale, 'live_ingestion.submit_button'),
      submitting: t(locale, 'live_ingestion.submitting'),
      submit_again_button: t(locale, 'live_ingestion.submit_again_button'),
      error_title: t(locale, 'live_ingestion.error_title'),
      error_body: t(locale, 'live_ingestion.error_body'),
      error_detail_label: t(locale, 'live_ingestion.error_detail_label'),
      evidence_label: t(locale, 'live_ingestion.evidence_label'),
      idle_hint: t(locale, 'live_ingestion.idle_hint'),
      timeline_title: t(locale, 'live_ingestion.timeline_title'),
      diff_title: t(locale, 'live_ingestion.diff_title'),
      diff_tag_before: t(locale, 'live_ingestion.diff_tag_before'),
      diff_tag_after: t(locale, 'live_ingestion.diff_tag_after'),
      redaction_entities_title: t(locale, 'live_ingestion.redaction_entities_title'),
      redaction_entity_kinds: {
        pii_name: t(locale, 'live_ingestion.redaction_entity_kinds.pii_name'),
        pii_id: t(locale, 'live_ingestion.redaction_entity_kinds.pii_id'),
        pii_phone: t(locale, 'live_ingestion.redaction_entity_kinds.pii_phone'),
        pii_email: t(locale, 'live_ingestion.redaction_entity_kinds.pii_email'),
        pii_account: t(locale, 'live_ingestion.redaction_entity_kinds.pii_account'),
        pii_address: t(locale, 'live_ingestion.redaction_entity_kinds.pii_address'),
      },
      redaction_no_entities: t(locale, 'live_ingestion.redaction_no_entities'),
      redaction_policy_footer: t(locale, 'live_ingestion.redaction_policy_footer'),
      dq_title: t(locale, 'live_ingestion.dq_title'),
      dq_errors_label: t(locale, 'live_ingestion.dq_errors_label'),
      dq_warnings_label: t(locale, 'live_ingestion.dq_warnings_label'),
      dq_suggested_label: t(locale, 'live_ingestion.dq_suggested_label'),
      dq_empty: t(locale, 'live_ingestion.dq_empty'),
      dq_policy_footer: t(locale, 'live_ingestion.dq_policy_footer'),
      ids_title: t(locale, 'live_ingestion.ids_title'),
      complaint_id_label: t(locale, 'live_ingestion.complaint_id_label'),
      raw_id_label: t(locale, 'live_ingestion.raw_id_label'),
      agent_run_id_label: t(locale, 'live_ingestion.agent_run_id_label'),
      event_id_label: t(locale, 'live_ingestion.event_id_label'),
      event_id_pending: t(locale, 'live_ingestion.event_id_pending'),
      events: {
        received: t(locale, 'live_ingestion.events.received'),
        institution_authenticated_simulated: t(
          locale,
          'live_ingestion.events.institution_authenticated_simulated',
        ),
        schema_validated: t(locale, 'live_ingestion.events.schema_validated'),
        pii_redacted: t(locale, 'live_ingestion.events.pii_redacted'),
        canonical_complaint_persisted: t(
          locale,
          'live_ingestion.events.canonical_complaint_persisted',
        ),
        data_quality_checks_completed: t(
          locale,
          'live_ingestion.events.data_quality_checks_completed',
        ),
        finding_triage_event_emitted: t(
          locale,
          'live_ingestion.events.finding_triage_event_emitted',
        ),
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
        <CockpitClient
          initialSnapshot={snapshot}
          labels={labels}
          csrfToken={session.csrfToken}
        />
      </div>
    </main>
  );
}
