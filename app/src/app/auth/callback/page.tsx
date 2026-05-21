import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Placeholder. The OAuth callback handler lands with the OAuth commit
// (next). The route is reserved here so that Keycloak's allowed-redirect
// list and the FastAPI reverse proxy can be configured to point at
// /app/auth/callback before the handler itself ships.
export default function AuthCallbackPage() {
  const locale = currentLocale();
  return (
    <main>
      <h1>{t(locale, 'auth.callback_title')}</h1>
      <p>{t(locale, 'auth.callback_body')}</p>
    </main>
  );
}
