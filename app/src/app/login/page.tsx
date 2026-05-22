import Link from 'next/link';

import { authConfig } from '@/auth/config';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

interface LoginPageProps {
  searchParams: { error?: string };
}

// /app/login — sign-in affordance. The actual OAuth round-trip is
// kicked off by GET /app/api/auth/login (the link below). WS1 styles
// this page; the structure is what matters for now.
//
// Demo mode adds a single "enter demo" affordance that loads tokens
// for all three personas in one round-trip. Production builds have
// SBS_DEMO_MODE off, the block below renders nothing, and the route
// /api/auth/demo-login returns 404.
export default function LoginPage({ searchParams }: LoginPageProps) {
  const locale = currentLocale();
  const errorCode = searchParams.error;

  return (
    <main>
      <h1>{t(locale, 'auth.signin')}</h1>
      {errorCode ? <p role="alert">{t(locale, 'auth.signin_failed')}</p> : null}
      <Link href="/api/auth/login">{t(locale, 'auth.signin')}</Link>

      {authConfig.demoMode ? (
        <section aria-label="demo">
          <h2>{t(locale, 'auth.demo_section_title')}</h2>
          <p>{t(locale, 'auth.demo_section_body')}</p>
          <Link href="/api/auth/demo-login">{t(locale, 'auth.demo_enter')}</Link>
        </section>
      ) : null}
    </main>
  );
}
