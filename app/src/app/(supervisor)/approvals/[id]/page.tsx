import { cookies } from 'next/headers';
import { notFound, redirect } from 'next/navigation';
import Link from 'next/link';

import { SESSION_COOKIE } from '@/auth/cookies';
import { activePersona, getSession } from '@/auth/session';
import { DecisionActionsRow } from '@/components/approvals/DecisionActionsRow';
import { PinnedEvidencePanel } from '@/components/approvals/PinnedEvidencePanel';
import { AgentReasoningPanel } from '@/components/findings/AgentReasoningPanel';
import { ClassificationPanel } from '@/components/findings/ClassificationPanel';
import { FeatureImportancePanel } from '@/components/findings/FeatureImportancePanel';
import { NarrativePanel } from '@/components/findings/NarrativePanel';
import { Badge, Card, CardBody, CardHeader, CardTitle } from '@/components/ui';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';
import { internalGet } from '@/lib/api';
import type { ApprovalDetailResponse } from '@/types/approvals';

export const dynamic = 'force-dynamic';

export default async function ApprovalDetailPage({
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

  let detail: ApprovalDetailResponse;
  try {
    detail = await internalGet<ApprovalDetailResponse>(
      `/v1/internal/approvals/${encodeURIComponent(params.id)}`,
      { roles: persona.roles },
    );
  } catch {
    notFound();
  }
  const { pending_approval, finding } = detail;

  const decisionActionsLabels = {
    approve: t(locale, 'approvals.actions.approve'),
    approve_with_edits: t(locale, 'approvals.actions.approve_with_edits'),
    reject: t(locale, 'approvals.actions.reject'),
    send_back: t(locale, 'approvals.actions.send_back'),
    confirm: t(locale, 'approvals.actions.confirm'),
    cancel: t(locale, 'approvals.actions.cancel'),
    already_decided: t(locale, 'approvals.decision_already_made'),
    decision_recorded: t(locale, 'approvals.decision_recorded'),
    reject_modal: {
      title: t(locale, 'approvals.rationale_modal.title_reject'),
      description: t(locale, 'approvals.rationale_modal.title_reject'),
      label: t(locale, 'approvals.rationale_modal.label'),
      placeholder: t(locale, 'approvals.rationale_modal.placeholder'),
      min_chars_helper: t(locale, 'approvals.rationale_modal.min_chars_helper'),
      char_count_template: t(locale, 'approvals.rationale_modal.char_count'),
    },
    send_back_modal: {
      title: t(locale, 'approvals.rationale_modal.title_send_back'),
      description: t(locale, 'approvals.rationale_modal.title_send_back'),
      label: t(locale, 'approvals.rationale_modal.label'),
      placeholder: t(locale, 'approvals.rationale_modal.placeholder'),
      min_chars_helper: t(locale, 'approvals.rationale_modal.min_chars_helper'),
      char_count_template: t(locale, 'approvals.rationale_modal.char_count'),
    },
    edit_modal: {
      title: t(locale, 'approvals.edit_modal.title'),
      narrative_label: t(locale, 'approvals.edit_modal.narrative_label'),
      rationale_label: t(locale, 'approvals.edit_modal.rationale_label'),
      min_chars_helper: t(locale, 'approvals.edit_modal.min_chars_helper'),
    },
  };

  return (
    <main className="mx-auto max-w-6xl space-y-4 p-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <Link href="/approvals" className="text-xs text-fg-link hover:underline">
            ← {t(locale, 'approvals.title')}
          </Link>
          <span className="text-fg-muted">·</span>
          <h1 className="font-mono text-lg text-fg">{finding.complaint.complaint_id}</h1>
          <Badge variant={pending_approval.severity}>{pending_approval.severity}</Badge>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>{t(locale, 'approvals.actions.approve')}</CardTitle>
        </CardHeader>
        <CardBody>
          <DecisionActionsRow
            approvalId={pending_approval.id}
            currentNarrative={finding.current_narrative ?? finding.complaint.narrative_text}
            initialStatus={pending_approval.status}
            initialDecisionAction={pending_approval.decision_action}
            csrfToken={session.csrfToken}
            labels={decisionActionsLabels}
          />
        </CardBody>
      </Card>

      <PinnedEvidencePanel
        evidence={detail.pinned_evidence}
        locale={locale}
        labels={{
          title: t(locale, 'approvals.panels.pinned_evidence'),
          regex_hits: t(locale, 'approvals.panels.regex_hits'),
          top_features: t(locale, 'approvals.panels.top_features'),
          cross_source: t(locale, 'approvals.panels.cross_source'),
        }}
      />

      <NarrativePanel
        text={finding.complaint.narrative_text}
        redactions={finding.anonymization?.redactions ?? []}
        anonymization={finding.anonymization}
        locale={locale}
        labels={{
          title: t(locale, 'findings.panels.narrative'),
          anonymization: t(locale, 'findings.panels.narrative_anonymization'),
          length: t(locale, 'findings.panels.narrative_length'),
        }}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ClassificationPanel
          classification={finding.classification}
          locale={locale}
          labels={{
            title: t(locale, 'findings.panels.classification'),
            top_k: t(locale, 'findings.panels.classification_top_k'),
            model: t(locale, 'findings.panels.classification_model'),
          }}
        />
        <FeatureImportancePanel
          features={finding.features}
          locale={locale}
          labels={{
            title: t(locale, 'findings.panels.feature_importance'),
            model: t(locale, 'findings.panels.feature_model'),
            rank_band: t(locale, 'findings.panels.rank_band'),
          }}
        />
      </div>

      <AgentReasoningPanel
        runs={finding.agent_runs}
        locale={locale}
        labels={{
          title: t(locale, 'findings.panels.agent_reasoning'),
          status: {
            success: t(locale, 'findings.agent_status.success'),
            partial: t(locale, 'findings.agent_status.partial'),
            failed: t(locale, 'findings.agent_status.failed'),
            timeout: t(locale, 'findings.agent_status.timeout'),
          },
        }}
      />

      {detail.decision_history.observations.length > 0 ||
      detail.decision_history.feedback.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>{t(locale, 'approvals.panels.decision_history')}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-3">
            {detail.decision_history.observations.map(o => (
              <div key={`o-${o.id}`} className="text-2xs text-fg-muted">
                <span className="font-medium text-fg">{o.approved_by}</span> · {o.approved_at}
              </div>
            ))}
            {detail.decision_history.feedback.map(f => (
              <div key={`f-${f.id}`} className="text-2xs text-fg-muted">
                <span className="font-medium text-fg">{f.decision}</span> ·{' '}
                {f.recorded_by} · {f.recorded_at}
                <p className="mt-1 text-fg">{f.rationale}</p>
              </div>
            ))}
          </CardBody>
        </Card>
      ) : null}
    </main>
  );
}
