import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. WS5 lands the approval detail view + four actions
// (approve, approve-with-edits, reject, send-back-to-analyst).
export default function ApprovalDetailPage({ params }: { params: { id: string } }) {
  const locale = currentLocale();
  return (
    <main>
      <h1>
        {t(locale, 'approvals.title')} · {params.id}
      </h1>
      <p>{t(locale, 'approvals.placeholder.detail_body')}</p>
    </main>
  );
}
