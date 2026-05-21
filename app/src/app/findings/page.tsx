import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. WS4 lands the findings list view + drilldown linkage.
export default function FindingsPage() {
  const locale = currentLocale();
  return (
    <main>
      <h1>{t(locale, 'findings.title')}</h1>
      <p>{t(locale, 'findings.placeholder.list_body')}</p>
    </main>
  );
}
