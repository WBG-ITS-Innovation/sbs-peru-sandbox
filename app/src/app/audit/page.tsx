import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. WS6 lands the read-only audit table (50 rows / page,
// actor / action / object / diff columns, search by actor / action / object).
export default function AuditPage() {
  const locale = currentLocale();
  return (
    <main>
      <h1>{t(locale, 'audit.title')}</h1>
      <p>{t(locale, 'audit.placeholder.body')}</p>
    </main>
  );
}
