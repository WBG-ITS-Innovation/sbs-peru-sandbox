import { redirect } from 'next/navigation';

import { activePersona } from '@/auth/persona-server';
import { PersonaPicker } from '@/components/persona/PersonaPicker';
import { currentLocale } from '@/i18n/server';
import { bi } from '@/lib/bi';

export const dynamic = 'force-dynamic';

// Demo entry point. If a persona cookie is already set, jump straight to
// that dashboard; otherwise show the 5-persona picker. This is the
// cookie/stub demo path and is independent of the Keycloak SSO on /login.
export default function DashboardIndexPage() {
  const active = activePersona();
  if (active) {
    redirect(`/dashboard/${active.slug}`);
  }
  const locale = currentLocale();
  return (
    <div className="mx-auto flex min-h-[70vh] w-full max-w-md flex-col justify-center p-4">
      <h1 className="text-xl font-semibold tracking-tight text-fg">
        {bi(locale, 'Cabina SupTech — demo', 'SupTech Cockpit — demo')}
      </h1>
      <p className="mt-1 text-xs text-fg-muted">
        {bi(locale, 'Elige una persona para entrar a su tablero.', 'Pick a persona to enter its dashboard.')}
      </p>
      <div className="mt-4">
        <PersonaPicker locale={locale} />
      </div>
    </div>
  );
}
