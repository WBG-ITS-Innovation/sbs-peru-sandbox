import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. The OAuth commit (next) replaces this with the Keycloak
// redirect flow + SBS-branded login affordance.
export default function LoginPage() {
  const locale = currentLocale();
  return (
    <main>
      <h1>{t(locale, 'auth.signin')}</h1>
      <p>{t(locale, 'auth.signing_in')}</p>
    </main>
  );
}
