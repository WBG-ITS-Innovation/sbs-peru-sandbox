import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. WS1 lands the visual design system index — every themed
// shadcn/ui component variant on one page so reviewers can audit the
// palette, typography, density, and severity tokens without opening
// every screen.
export default function ComponentIndexPage() {
  const locale = currentLocale();
  return (
    <main>
      <h1>{t(locale, 'components_index.title')}</h1>
      <p>{t(locale, 'components_index.placeholder.body')}</p>
    </main>
  );
}
