// Language toggle (ES ↔ EN). Writes the sbs-locale cookie via a server
// action so server components see the new locale on next render.

'use client';

import { useTransition } from 'react';

import { setLocaleAction } from '@/auth/actions/set-locale';
import { Button } from '@/components/ui';
import type { Locale } from '@/i18n';

interface LanguageToggleProps {
  currentLocale: Locale;
  labels: { es: string; en: string; toggle: string };
}

export function LanguageToggle({ currentLocale, labels }: LanguageToggleProps) {
  const [isPending, startTransition] = useTransition();

  const switchTo = (target: Locale) => {
    if (target === currentLocale || isPending) return;
    startTransition(async () => {
      await setLocaleAction(target);
    });
  };

  return (
    <div
      role="group"
      aria-label={labels.toggle}
      className="inline-flex items-center rounded-sbs border border-border-subtle bg-surface-subtle"
    >
      <Button
        variant={currentLocale === 'es-PE' ? 'default' : 'ghost'}
        size="sm"
        aria-pressed={currentLocale === 'es-PE'}
        onClick={() => switchTo('es-PE')}
        disabled={isPending}
        className="h-7 rounded-r-none"
      >
        {labels.es}
      </Button>
      <Button
        variant={currentLocale === 'en-US' ? 'default' : 'ghost'}
        size="sm"
        aria-pressed={currentLocale === 'en-US'}
        onClick={() => switchTo('en-US')}
        disabled={isPending}
        className="h-7 rounded-l-none"
      >
        {labels.en}
      </Button>
    </div>
  );
}
