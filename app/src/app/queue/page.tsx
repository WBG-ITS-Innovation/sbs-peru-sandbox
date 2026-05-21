import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. WS6 lands the risk queue table + filters + assignment.
export default function QueuePage() {
  const locale = currentLocale();
  return (
    <main>
      <h1>{t(locale, 'queue.title')}</h1>
      <p>{t(locale, 'queue.placeholder.body')}</p>
    </main>
  );
}
