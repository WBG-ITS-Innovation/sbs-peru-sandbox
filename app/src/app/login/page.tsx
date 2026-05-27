import Link from 'next/link';

import { authConfig } from '@/auth/config';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

interface LoginPageProps {
  searchParams: { error?: string };
}

// /app/login — standalone sign-in page. No supervisor rail. The OAuth
// round-trip is still kicked off by GET /app/api/auth/login; demo mode
// adds a single affordance that loads tokens for all three personas in
// one round-trip. We preserve every backend route and behaviour and
// just refresh the visual.
export default function LoginPage({ searchParams }: LoginPageProps) {
  const locale = currentLocale();
  const errorCode = searchParams.error;

  const title = t(locale, 'login.title');
  const subtitle = t(locale, 'login.subtitle');
  const ssoButton = t(locale, 'login.sso_button');
  const demoButton = t(locale, 'login.demo_button');
  const demoSubline = t(locale, 'login.demo_subline');
  const integratorLink = t(locale, 'login.integrator_link');
  const mfaNotice = t(locale, 'login.mfa_notice');
  const footerVersion = t(locale, 'login.footer_version');
  const footerLocation = t(locale, 'login.footer_location');
  const secureSession = t(locale, 'login.secure_session');
  const lockup = t(locale, 'common.lockup');
  const pilotBadge = t(locale, 'pilot.badge');
  const signinFailed = t(locale, 'auth.signin_failed');

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-brand-navy px-4 py-10 text-fg">
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 flex h-1.5"
      >
        <div className="h-full flex-1 bg-[#d91023]" />
        <div className="h-full flex-1 bg-white" />
        <div className="h-full flex-1 bg-[#d91023]" />
      </div>

      <span className="absolute right-4 top-4 rounded-sbs border border-brand-gold/50 bg-brand-navy px-2 py-0.5 font-mono text-2xs uppercase tracking-wider text-brand-gold">
        {pilotBadge}
      </span>

      <span className="absolute left-4 top-4 hidden max-w-[60%] truncate font-mono text-2xs uppercase tracking-wider text-fg-inverted/70 sm:block">
        {lockup}
      </span>

      <section
        aria-labelledby="login-title"
        className="w-full max-w-2xl rounded-sbs border border-border bg-surface p-12 shadow-lg"
      >
        <div className="mb-8 flex flex-col items-center">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/app/sbs-logo.png"
            alt="SBS"
            className="h-16 w-auto"
          />
          <h1
            id="login-title"
            className="mt-5 text-center text-xl font-semibold tracking-tight text-fg"
          >
            {title}
          </h1>
          <p className="mt-2 text-center text-sm text-fg-muted">{subtitle}</p>
        </div>

        {errorCode ? (
          <p
            role="alert"
            className="mb-3 rounded-sbs border border-severity-high-border bg-severity-high-bg px-3 py-2 text-xs text-severity-high-fg"
          >
            {signinFailed}
          </p>
        ) : null}

        <Link
          href="/api/auth/login"
          className="flex h-12 w-full items-center justify-center rounded-sbs bg-brand-navy px-4 text-base font-semibold text-fg-inverted transition-colors hover:bg-brand-navy/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2"
        >
          {ssoButton}
        </Link>

        {authConfig.demoMode ? (
          <div className="mt-5 border-t border-border pt-4">
            <Link
              href="/api/auth/demo-login"
              className="flex h-10 w-full items-center justify-center rounded-sbs border border-border-strong bg-surface px-3 text-sm font-medium text-fg transition-colors hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2"
            >
              {demoButton}
            </Link>
            <p className="mt-2 text-2xs leading-snug text-fg-muted">{demoSubline}</p>
          </div>
        ) : null}

        <p className="mt-4 font-mono text-2xs leading-snug text-fg-subtle">{mfaNotice}</p>

        <div className="mt-4 border-t border-border pt-3 text-center">
          <Link
            href="/developers"
            className="text-xs text-fg-link underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2"
          >
            {integratorLink}
          </Link>
        </div>

        <div className="mt-6 border-t border-border pt-3 text-center font-mono text-2xs leading-relaxed text-fg-subtle">
          <div>{footerVersion}</div>
          <div>{footerLocation}</div>
        </div>
      </section>

      <span className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-1.5 font-mono text-2xs uppercase tracking-wider text-fg-inverted/60">
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-severity-low-border" />
        {secureSession}
      </span>
    </main>
  );
}
