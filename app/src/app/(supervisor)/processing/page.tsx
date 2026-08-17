// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { ProcessingListClient } from '@/components/processing/ProcessingListClient';
import { PageHeader } from '@/components/shell/PageHeader';
import { currentLocale } from '@/i18n/server';

// /app/processing — list of recently ingested complaints with their
// agent-pipeline state. Click into one for the live drill-in view.

export const dynamic = 'force-dynamic';

export default async function ProcessingPage() {
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const locale = await currentLocale();
  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={['Supervisión', 'Procesamiento']}
        title={locale === 'es-PE' ? 'Procesamiento de reclamos' : 'Complaint processing'}
        subtitle={
          locale === 'es-PE'
            ? 'Cada reclamo recibido por SBS pasa por una tubería de ingesta y 3 agentes. Aquí ves el estado en vivo de los reclamos en curso y el historial de los completados.'
            : 'Each complaint received by SBS goes through an ingestion pipeline and 3 agents. Watch live status of in-flight complaints and the completed history.'
        }
      />
      <div className="mx-auto w-full max-w-7xl px-6 py-4">
        <ProcessingListClient locale={locale} />
      </div>
    </main>
  );
}
