// SPDX-License-Identifier: Apache-2.0
// Top bar. Institutional navy band — white SBS diamond on a navy
// plaque, lockup in mono caps, then ConnectionStateDot · language
// toggle · (demo-mode) persona switcher on the right. ADR 0040 §D5
// places the ConnectionStateDot here so every screen shows the SSE
// state without each screen having to render its own. The visual
// language matches the Claude Design artifact: a 56–64px navy band
// that says "regulator dashboard" the moment the screen loads.

'use client';

import { ConnectionStateDot } from '@/components/cockpit/ConnectionStateDot';
import { useConnectionState } from '@/hooks/useConnectionState';
import type { Locale } from '@/i18n';
import { cn } from '@/lib/cn';

import { LanguageToggle } from './LanguageToggle';
import { PersonaSwitcher } from './PersonaSwitcher';

interface TopBarProps {
  lockup: string;
  locale: Locale;
  demoMode: boolean;
  activePersonaKey: 'maria' | 'lucia' | 'jorge' | null;
  csrfToken: string | null;
  labels: {
    connectionLabel: { connecting: string; connected: string; disconnected: string };
    languageToggle: { es: string; en: string; toggle: string };
    persona: {
      switch_persona: string;
      active_persona: string;
      maria: string;
      lucia: string;
      jorge: string;
      cancel: string;
    };
  };
}

export function TopBar({
  lockup,
  locale,
  demoMode,
  activePersonaKey,
  csrfToken,
  labels,
}: TopBarProps) {
  const connectionState = useConnectionState('cockpit');

  return (
    <header
      className={cn(
        'flex h-16 items-center justify-between gap-4 px-5',
        'bg-brand-navy text-fg-inverted',
        'border-b border-brand-navy/40 shadow-[inset_0_-1px_0_rgba(255,255,255,0.05)]',
      )}
    >
      <div className="flex min-w-0 items-center gap-3">
        <div
          className="flex h-12 flex-shrink-0 items-center bg-white px-3"
          aria-label="SBS"
          role="img"
        >
          {/* Logo image already includes "Superintendencia de Banca,
              Seguros y AFP · República del Perú", so the alt covers
              the same wording for assistive tech and we don't repeat
              it as a text lockup next to the image. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src="/app/sbs-logo.png"
            alt={lockup}
            className="h-9 w-auto"
          />
        </div>
      </div>
      <div
        // The retinting rules live in app/src/app/globals.css under
        // [data-on-navy]; using a data attribute keeps the override
        // out of arbitrary-variant strings that don't always make it
        // through the Tailwind compiler.
        data-on-navy=""
        className="flex items-center gap-3"
      >
        <ConnectionStateDot state={connectionState} label={labels.connectionLabel} />
        <LanguageToggle currentLocale={locale} labels={labels.languageToggle} />
        {demoMode && activePersonaKey && csrfToken ? (
          <PersonaSwitcher
            activePersonaKey={activePersonaKey}
            labels={labels.persona}
            csrfToken={csrfToken}
          />
        ) : null}
      </div>
    </header>
  );
}
