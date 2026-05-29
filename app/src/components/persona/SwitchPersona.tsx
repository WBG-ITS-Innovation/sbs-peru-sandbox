'use client';

import { useRouter } from 'next/navigation';
import { useTransition } from 'react';

import { clearPersonaAction } from '@/app/dashboard/actions';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

// Clears the active-persona cookie and returns to the picker, so the
// demo can switch from Jorge to Sergio without a Keycloak round-trip.
export function SwitchPersona({ locale }: { locale: Locale }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  return (
    <button
      type="button"
      disabled={pending}
      onClick={() =>
        start(async () => {
          await clearPersonaAction();
          router.push('/dashboard');
          router.refresh();
        })
      }
      className="rounded-sbs border border-fg-inverted/30 px-2.5 py-1 text-xs font-medium hover:bg-white/10 disabled:opacity-50"
    >
      {bi(locale, 'Cambiar persona', 'Switch persona')}
    </button>
  );
}
