// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { SandboxAdmin } from '@/components/sandbox/SandboxAdmin';
import { PageHeader } from '@/components/shell/PageHeader';
import { currentLocale } from '@/i18n/server';

// IT / sandbox-admin view. Real controllable surfaces + real data only:
// ingestion controls (link to the working /sandbox panels), the seeded
// institutions' real credential state, recent submissions (real feed), and
// the real audit log.
export const dynamic = 'force-dynamic';

export default async function AdminPage() {
  if (!getSession((await cookies()).get(SESSION_COOKIE)?.value)) {
    redirect('/login');
  }
  const locale = await currentLocale();
  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={[locale === 'es-PE' ? 'Sandbox' : 'Sandbox', locale === 'es-PE' ? 'Administración (IT)' : 'Administration (IT)']}
        title={locale === 'es-PE' ? 'Administración del sandbox (IT)' : 'Sandbox administration (IT)'}
        subtitle={
          locale === 'es-PE'
            ? 'Parámetros reales que sí afectan el sistema, estado de credenciales de las instituciones, envíos recientes y la bitácora de auditoría — todo en vivo.'
            : 'Real parameters that actually affect the system, institution credential state, recent submissions, and the audit log — all live.'
        }
      />
      <div className="mx-auto w-full max-w-screen-2xl px-6 py-4">
        <SandboxAdmin locale={locale} />
      </div>
    </main>
  );
}
