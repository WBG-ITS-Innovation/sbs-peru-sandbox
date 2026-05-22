import Link from 'next/link';

import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

interface LoginPageProps {
  searchParams: { error?: string };
}

// /app/login — sign-in affordance. The actual OAuth round-trip is
// kicked off by GET /app/api/auth/login (the link below). WS1 styles
// this page; the structure is what matters for now.
export default function LoginPage({ searchParams }: LoginPageProps) {
  const locale = currentLocale();
  const errorCode = searchParams.error;

  return (
    <main>
      <h1>{t(locale, 'auth.signin')}</h1>
      {errorCode ? <p role="alert">{t(locale, 'auth.signin_failed')}</p> : null}
      <Link href="/api/auth/login">{t(locale, 'auth.signin')}</Link>
    </main>
  );
}
