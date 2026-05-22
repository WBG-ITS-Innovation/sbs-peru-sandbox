// Top bar. Institutional lockup left; language toggle + connection
// dot + (demo-mode) persona switcher right. ADR 0040 §D5 places the
// ConnectionStateDot here so every screen shows the SSE state without
// each screen having to render its own.

'use client';

import { ConnectionStateDot } from '@/components/cockpit/ConnectionStateDot';
import { useConnectionState } from '@/hooks/useConnectionState';
import type { Locale } from '@/i18n';

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
    <header className="flex h-14 items-center justify-between gap-4 border-b border-border bg-surface px-4">
      <div className="flex min-w-0 items-center gap-3">
        <span className="truncate text-xs font-medium text-fg-muted">{lockup}</span>
      </div>
      <div className="flex items-center gap-3">
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
