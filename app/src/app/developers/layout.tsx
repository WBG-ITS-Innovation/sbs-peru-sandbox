import Link from 'next/link';
import { Book, Clock, Key, Server } from 'lucide-react';

import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Institution-facing Developer Portal. This shell is intentionally
// separate from the supervisor shell — it does NOT mount the supervisor
// NavRail, and it does NOT require an SBS supervisor session. The
// portal pages are preview-only at this stage (no real onboarding API
// is wired in). Authentication for integrators is out of scope here.

export const dynamic = 'force-dynamic';

export default function DevelopersLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = currentLocale();
  const headerTitle = t(locale, 'developers.header_title');
  const headerSubtitle = t(locale, 'developers.header_subtitle');
  const lockup = t(locale, 'common.lockup');
  const sessionLabel = t(locale, 'developers.session_label');
  const subnavPortal = t(locale, 'developers.subnav.portal');
  const subnavCredentials = t(locale, 'developers.subnav.credentials');
  const subnavStatus = t(locale, 'developers.subnav.status');
  const subnavChangelog = t(locale, 'developers.subnav.changelog');
  const attribution = t(locale, 'common.delivered_by');
  const pilotBadge = t(locale, 'pilot.badge');

  return (
    <div className="flex min-h-screen flex-col bg-surface text-fg">
      <header className="bg-brand-navy text-fg-inverted">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <div
              aria-hidden="true"
              className="flex h-9 w-9 rotate-45 items-center justify-center rounded-sbs border border-brand-gold bg-brand-navy text-brand-gold"
            >
              <span className="-rotate-45 font-serif text-base font-semibold">S</span>
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-mono uppercase tracking-wider text-fg-inverted/80">
                {lockup}
              </p>
              <h1 className="truncate text-sm font-semibold">
                {headerTitle}
              </h1>
              <p className="truncate text-2xs text-fg-inverted/70">{headerSubtitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 font-mono text-2xs uppercase tracking-wider text-fg-inverted/70">
              <span
                aria-hidden="true"
                className="h-1.5 w-1.5 rounded-full bg-severity-low-border"
              />
              {sessionLabel}
            </span>
            <span className="rounded-sbs border border-brand-gold/50 px-2 py-0.5 font-mono text-2xs uppercase tracking-wider text-brand-gold">
              {pilotBadge}
            </span>
          </div>
        </div>
        <nav
          aria-label="Developer portal subnav"
          className="mx-auto flex max-w-7xl gap-4 border-t border-brand-navy/30 px-4"
        >
          <Link
            href="/developers"
            className="flex items-center gap-1.5 border-b-2 border-brand-cyan px-1 py-2 text-xs text-fg-inverted"
          >
            <Book className="h-3.5 w-3.5" aria-hidden="true" />
            {subnavPortal}
          </Link>
          <Link
            href="/developers/credentials"
            className="flex items-center gap-1.5 border-b-2 border-transparent px-1 py-2 text-xs text-fg-inverted/70 hover:text-fg-inverted"
          >
            <Key className="h-3.5 w-3.5" aria-hidden="true" />
            {subnavCredentials}
          </Link>
          <span
            aria-disabled="true"
            className="flex items-center gap-1.5 border-b-2 border-transparent px-1 py-2 text-xs text-fg-inverted/40"
          >
            <Server className="h-3.5 w-3.5" aria-hidden="true" />
            {subnavStatus}
          </span>
          <span
            aria-disabled="true"
            className="flex items-center gap-1.5 border-b-2 border-transparent px-1 py-2 text-xs text-fg-inverted/40"
          >
            <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            {subnavChangelog}
          </span>
        </nav>
      </header>
      <div className="flex-1">{children}</div>
      <footer className="border-t border-border bg-surface-subtle px-4 py-2 text-2xs text-fg-muted">
        {attribution}
      </footer>
    </div>
  );
}
