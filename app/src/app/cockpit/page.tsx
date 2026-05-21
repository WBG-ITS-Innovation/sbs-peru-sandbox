import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. WS3 lands the cockpit hero view (Tier 1 / Tier 2
// side-by-side, cross-source fusion strip, anomaly cards, SSE wiring).
export default function CockpitPage() {
  const locale = currentLocale();
  return (
    <main>
      <h1>{t(locale, 'cockpit.title')}</h1>
      <p>{t(locale, 'cockpit.placeholder.body')}</p>
    </main>
  );
}
