'use client';

import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';

import { setPersonaAction } from '@/app/dashboard/actions';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import { PERSONA_SLUGS, PERSONAS, personaTitle } from '@/lib/persona';

// Demo persona picker (P-RESHAPE-10). Sets the active-persona cookie via
// a server action, then routes to that persona's dashboard. This is the
// stub-auth demo path; it leaves the Keycloak SSO flow above untouched.
export function PersonaPicker({ locale }: { locale: Locale }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [active, setActive] = useState<string | null>(null);

  function pick(slug: string) {
    setActive(slug);
    start(async () => {
      await setPersonaAction(slug);
      router.push(`/dashboard/${slug}`);
    });
  }

  return (
    <div className="mt-5 border-t border-border pt-4">
      <p className="mb-2 text-2xs font-medium uppercase tracking-wide text-fg-subtle">
        {bi(locale, 'Demo — elegir persona', 'Demo — pick a persona')}
      </p>
      <div className="grid grid-cols-1 gap-1.5">
        {PERSONA_SLUGS.map((slug) => {
          const p = PERSONAS[slug];
          return (
            <button
              key={slug}
              type="button"
              disabled={pending}
              onClick={() => pick(slug)}
              className="flex items-center justify-between rounded-sbs border border-border bg-surface px-3 py-2 text-left transition-colors hover:border-brand-cyan hover:bg-surface-subtle focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus disabled:opacity-50"
            >
              <span className="text-sm font-semibold text-fg">{p.name}</span>
              <span className="text-2xs text-fg-muted">
                {active === slug && pending
                  ? bi(locale, 'Entrando…', 'Entering…')
                  : personaTitle(p, locale)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
