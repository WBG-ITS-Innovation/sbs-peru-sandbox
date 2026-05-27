import { cookies } from 'next/headers';
import { notFound, redirect } from 'next/navigation';
import Link from 'next/link';

import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';
import { ActionsRow } from '@/components/findings/ActionsRow';
import { AgentReasoningPanel } from '@/components/findings/AgentReasoningPanel';
import { ClassificationPanel } from '@/components/findings/ClassificationPanel';
import { DraftNarrativeEditor } from '@/components/findings/DraftNarrativeEditor';
import { ExecutiveBriefPanel } from '@/components/findings/ExecutiveBriefPanel';
import { FeatureImportancePanel } from '@/components/findings/FeatureImportancePanel';
import { FindingNavigator } from '@/components/findings/FindingNavigator';
import { NarrativePanel } from '@/components/findings/NarrativePanel';
import { TaxonomyPanel } from '@/components/findings/TaxonomyPanel';
import { Badge, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';
import { internalGet } from '@/lib/api';
import type { FindingDetailResponse } from '@/types/findings';

export const dynamic = 'force-dynamic';

export default async function FindingDetailPage({
  params,
}: {
  params: { id: string };
}) {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const persona = activePersona(session);
  const locale = currentLocale();

  let detail: FindingDetailResponse;
  try {
    detail = await internalGet<FindingDetailResponse>(
      `/v1/internal/findings/${encodeURIComponent(params.id)}`,
      { roles: persona.roles },
    );
  } catch {
    notFound();
  }

  const tierVariant: 'tier1' | 'tier2' =
    detail.complaint.source === 'api_realtime' ? 'tier1' : 'tier2';
  const tierLabel =
    tierVariant === 'tier1'
      ? t(locale, 'cockpit.tier_badges.tier1_nrt')
      : t(locale, 'cockpit.tier_badges.tier2_batch');

  const latestClassifierRunId =
    detail.agent_runs.find(r => r.agent_name === 'classifier')?.id ?? null;

  const hasResolutionData = Boolean(
    detail.complaint.estado_reclamo ||
      detail.complaint.tipo_resolucion ||
      detail.complaint.fecha_resolucion ||
      detail.complaint.monto_pendiente ||
      detail.complaint.descripcion_resolucion,
  );

  // Heuristic: surface "Open audit" with a warning if any agent_run
  // partial-completed or any DQ error fired (the navigator highlights
  // the audit link).
  const hasIssues =
    detail.agent_runs.some(r => r.status === 'partial' || r.status === 'failed') ||
    detail.agent_runs.some(r => Boolean(r.error));

  return (
    <main className="mx-auto max-w-6xl space-y-4 p-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <Link href="/findings" className="text-xs text-fg-link hover:underline">
            ← {t(locale, 'findings.title')}
          </Link>
          <span className="text-fg-muted">·</span>
          <h1 className="font-mono text-lg text-fg">{detail.complaint.complaint_id}</h1>
        </div>
      </header>

      <FindingNavigator
        locale={locale}
        complaintId={detail.complaint.complaint_id}
        hasIssues={hasIssues}
      />

      <Card>
        <CardHeader>
          <CardTitle>{t(locale, 'findings.panels.header')}</CardTitle>
        </CardHeader>
        <CardBody className="grid grid-cols-2 gap-3 text-2xs md:grid-cols-4">
          <Field label={t(locale, 'findings.columns.institution')} value={detail.complaint.institution_name} />
          <Field label={t(locale, 'findings.columns.source')}>
            <Badge variant={tierVariant} className="uppercase tracking-wider">
              {tierLabel}
            </Badge>
          </Field>
          <Field label={t(locale, 'findings.columns.received_at')}>
            <time className="tabular" dateTime={detail.complaint.received_at}>
              {new Intl.DateTimeFormat(locale, {
                timeZone: 'America/Lima',
                day: '2-digit',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
              }).format(new Date(detail.complaint.received_at))}
            </time>
          </Field>
          <Field label={t(locale, 'findings.columns.severity')}>
            <Badge variant={detail.complaint.severity}>{detail.complaint.severity}</Badge>
          </Field>
          <Field label="Motivo" value={detail.complaint.motivo_code} />
          <Field label="Producto" value={detail.complaint.product_category} />
          <Field label="Canal" value={detail.complaint.channel} />
          <Field label="Distrito" value={detail.complaint.complainant_district} />
        </CardBody>
      </Card>

      {hasResolutionData ? (
        <Card>
          <CardHeader>
            <CardTitle>{t(locale, 'findings.panels.resolution_section')}</CardTitle>
          </CardHeader>
          <CardBody className="grid grid-cols-2 gap-3 text-2xs md:grid-cols-4">
            {detail.complaint.estado_reclamo ? (
              <Field
                label={t(locale, 'findings.panels.resolution_state')}
                value={detail.complaint.estado_reclamo}
              />
            ) : null}
            {detail.complaint.tipo_resolucion ? (
              <Field
                label={t(locale, 'findings.panels.resolution_type')}
                value={detail.complaint.tipo_resolucion}
              />
            ) : null}
            {detail.complaint.fecha_resolucion ? (
              <Field
                label={t(locale, 'findings.panels.resolution_date')}
                value={detail.complaint.fecha_resolucion}
              />
            ) : null}
            {detail.complaint.monto_pendiente ? (
              <Field
                label={t(locale, 'findings.panels.pending_amount')}
                value={`S/ ${detail.complaint.monto_pendiente}`}
              />
            ) : null}
            {detail.complaint.descripcion_resolucion ? (
              <div className="col-span-2 md:col-span-4">
                <p className="uppercase tracking-wider text-fg-muted">
                  {t(locale, 'findings.panels.resolution_description')}
                </p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-fg">
                  {detail.complaint.descripcion_resolucion}
                </p>
              </div>
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      <TaxonomyPanel
        normalizations={detail.taxonomy_normalizations ?? []}
        dictionaryVersion={detail.taxonomy_dictionary_version ?? null}
        labels={{
          title: t(locale, 'findings.panels.taxonomy_title'),
          show: t(locale, 'findings.panels.taxonomy_show'),
          hide: t(locale, 'findings.panels.taxonomy_hide'),
          field: t(locale, 'findings.panels.taxonomy_field'),
          original: t(locale, 'findings.panels.taxonomy_original'),
          canonical: t(locale, 'findings.panels.taxonomy_canonical'),
          dictionary: t(locale, 'findings.panels.taxonomy_dictionary'),
          empty: t(locale, 'findings.panels.taxonomy_empty'),
        }}
      />

      <NarrativePanel
        text={detail.complaint.narrative_text}
        redactions={detail.anonymization?.redactions ?? []}
        anonymization={detail.anonymization}
        locale={locale}
        labels={{
          title: t(locale, 'findings.panels.narrative'),
          anonymization: t(locale, 'findings.panels.narrative_anonymization'),
          length: t(locale, 'findings.panels.narrative_length'),
        }}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ClassificationPanel
          classification={detail.classification}
          locale={locale}
          labels={{
            title: t(locale, 'findings.panels.classification'),
            top_k: t(locale, 'findings.panels.classification_top_k'),
            model: t(locale, 'findings.panels.classification_model'),
            confidence_degraded: t(locale, 'findings.panels.confidence_degraded'),
          }}
        />
        <FeatureImportancePanel
          features={detail.features}
          locale={locale}
          labels={{
            title: t(locale, 'findings.panels.feature_importance'),
            model: t(locale, 'findings.panels.feature_model'),
            rank_band: t(locale, 'findings.panels.rank_band'),
          }}
        />
      </div>

      <AgentReasoningPanel
        runs={detail.agent_runs}
        locale={locale}
        labels={{
          title: t(locale, 'findings.panels.agent_reasoning'),
          status: {
            in_progress: t(locale, 'findings.agent_status.in_progress'),
            success: t(locale, 'findings.agent_status.success'),
            partial: t(locale, 'findings.agent_status.partial'),
            failed: t(locale, 'findings.agent_status.failed'),
            timeout: t(locale, 'findings.agent_status.timeout'),
          },
        }}
      />

      <DraftNarrativeEditor
        complaintId={detail.complaint.complaint_id}
        initialText={detail.current_narrative ?? ''}
        agentDraftedText={detail.agent_drafted_narrative}
        csrfToken={session.csrfToken}
        actorId={persona.email}
        agentRunId={latestClassifierRunId}
        labels={{
          title: t(locale, 'findings.panels.draft_narrative'),
          save: t(locale, 'findings.actions.save_draft'),
          edit: t(locale, 'findings.actions.edit'),
          cancel: t(locale, 'findings.actions.cancel_edit'),
          agent_drafted: t(locale, 'findings.draft_helper.agent_drafted'),
          no_edits_yet: t(locale, 'findings.draft_helper.no_edits_yet'),
        }}
      />

      <ExecutiveBriefPanel
        summary={detail.executive_summary ?? null}
        labels={{
          title: t(locale, 'findings.panels.executive_brief'),
          show: t(locale, 'findings.panels.executive_brief_show'),
          hide: t(locale, 'findings.panels.executive_brief_hide'),
          audience: t(locale, 'findings.panels.executive_brief_audience'),
          key_points: t(locale, 'findings.panels.executive_brief_key_points'),
          model: t(locale, 'findings.panels.executive_brief_model'),
          empty: t(locale, 'findings.panels.executive_brief_empty'),
        }}
      />

      <ActionsRow
        complaintId={detail.complaint.complaint_id}
        severity={detail.complaint.severity}
        csrfToken={session.csrfToken}
        actorId={persona.email}
        agentRunId={latestClassifierRunId}
        pendingApprovalId={detail.pending_approval?.id ?? null}
        isHead={persona.roles.includes('sbs:conduct:head')}
        labels={{
          send_to_approvals: t(locale, 'findings.actions.send_to_approvals'),
          mark_false_positive: t(locale, 'findings.actions.mark_false_positive'),
          assign: t(locale, 'findings.actions.assign'),
          already_pending: t(locale, 'findings.actions.send_to_approvals_already_pending'),
          assignment_via_api: t(locale, 'findings.actions.assignment_via_api'),
        }}
      />
    </main>
  );
}

function Field({
  label,
  value,
  children,
}: {
  label: string;
  value?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="space-y-0.5">
      <p className="uppercase tracking-wider text-fg-muted">{label}</p>
      <div className="text-sm text-fg">{children ?? value ?? '—'}</div>
    </div>
  );
}
