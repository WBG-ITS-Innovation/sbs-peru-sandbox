import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. WS5 lands the approvals queue + decision KPIs.
export default function ApprovalsPage() {
  const locale = currentLocale();
  return (
    <main>
      <h1>{t(locale, 'approvals.title')}</h1>
      <p>{t(locale, 'approvals.placeholder.queue_body')}</p>
    </main>
  );
}
