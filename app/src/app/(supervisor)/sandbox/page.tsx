// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { LiveIngestionBanner } from '@/components/persona/LiveIngestionBanner';
import { SandboxControl } from '@/components/sandbox/SandboxControl';
import { PageHeader } from '@/components/shell/PageHeader';
import { currentLocale } from '@/i18n/server';

// Sandbox control surfaces — bank-side simulators that drive the REAL Tier-1
// granular endpoint and the REAL Tier-2 batch endpoint. Every control hits the
// real API and shows the real response. The same live-ingestion banner that
// the aggregates page uses sits on top, so a complaint sent from either panel
// appears here live.
export const dynamic = 'force-dynamic';

export default function SandboxPage() {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  if (!getSession(sessionId)) {
    redirect('/login');
  }
  const locale = currentLocale();
  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={[locale === 'es-PE' ? 'Sandbox' : 'Sandbox', locale === 'es-PE' ? 'Simulador de instituciones' : 'Institution simulator']}
        title={locale === 'es-PE' ? 'Simulador de instituciones — Tier 1 / Tier 2' : 'Institution simulator — Tier 1 / Tier 2'}
        subtitle={
          locale === 'es-PE'
            ? 'Controles del lado de la institución que envían reclamos por los endpoints REALES: Tier 1 (granular, firmado OAuth + HMAC + mTLS) y Tier 2 (lote CSV). Cada envío es una solicitud real y muestra la respuesta real del API.'
            : 'Institution-side controls that send complaints through the REAL endpoints: Tier 1 (granular, signed OAuth + HMAC + mTLS) and Tier 2 (CSV batch). Every send is a real request and shows the API\'s real response.'
        }
      />
      <div className="mx-auto w-full max-w-screen-2xl space-y-4 px-6 py-4">
        <LiveIngestionBanner locale={locale} />
        <SandboxControl locale={locale} />
      </div>
    </main>
  );
}
