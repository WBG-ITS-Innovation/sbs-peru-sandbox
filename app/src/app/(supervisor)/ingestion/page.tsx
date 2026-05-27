import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { IngestionClient } from '@/components/ingestion/IngestionClient';
import { PageHeader } from '@/components/shell/PageHeader';
import { currentLocale } from '@/i18n/server';
import emails from '@/lib/journey-emails.json';

// /app/ingestion — live ingestion theatre. A client-driven ticker sends
// SBS sample rows through the real signed pipeline at the configured
// interval, and a separate panel polls /v1/audit-fed recent-complaints
// data so the operator can see SBS receiving the traffic in real time.

export const dynamic = 'force-dynamic';

export default function IngestionPage() {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const locale = currentLocale();
  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={['Supervisión', 'Ingesta en vivo']}
        title={locale === 'es-PE' ? 'Ingesta en vivo' : 'Live ingestion'}
        subtitle={
          locale === 'es-PE'
            ? 'Teatro de ingesta. Envía reclamos sintéticos del muestreo SBS a la API sandbox y observa la recepción en SBS conforme van llegando.'
            : 'Ingestion theatre. Pump synthetic SBS sample rows into the sandbox API and watch SBS receive them in real time.'
        }
      />
      <div className="mx-auto w-full max-w-7xl px-6 py-4">
        <IngestionClient
          locale={locale}
          emails={emails as unknown as Array<Record<string, unknown>>}
          csrfToken={session.csrfToken}
        />
      </div>
    </main>
  );
}
