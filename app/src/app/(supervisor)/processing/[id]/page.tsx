// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { ProcessingDrilldown } from '@/components/processing/ProcessingDrilldown';
import { PageHeader } from '@/components/shell/PageHeader';
import { currentLocale } from '@/i18n/server';

export const dynamic = 'force-dynamic';

interface Props {
  params: Promise<{ id: string }>;
}

export default async function ProcessingDrilldownPage(props: Props) {
  const params = await props.params;
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const locale = await currentLocale();
  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={['Supervisión', 'Procesamiento', params.id]}
        title={
          locale === 'es-PE'
            ? `Reclamo ${params.id}`
            : `Complaint ${params.id}`
        }
        subtitle={
          locale === 'es-PE'
            ? 'Trazabilidad por etapas y por agente: PII, calidad de datos, taxonomía, clasificación, investigación y síntesis. Quién hizo qué y cuándo.'
            : 'Stage-by-stage and agent-by-agent traceability: PII, data quality, taxonomy, classification, investigation, synthesis. Who did what and when.'
        }
      />
      <div className="mx-auto w-full max-w-6xl px-6 py-4">
        <ProcessingDrilldown locale={locale} complaintId={params.id} />
      </div>
    </main>
  );
}
