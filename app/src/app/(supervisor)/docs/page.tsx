// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { DocsTabs } from '@/components/docs/DocsTabs';
import { PageHeader } from '@/components/shell/PageHeader';
import { currentLocale } from '@/i18n/server';

// /app/docs — documentation hub for the SBS demo. Four tabs:
//   - Arquitectura (architecture diagram + 8 numbered steps)
//   - API para integradores (curl + python + auth chain snippets)
//   - Modelo Anexo 1-A (27 fields reference)
//   - Agentes y herramientas (5 agents, 10 tools)

export const dynamic = 'force-dynamic';

export default async function DocsPage() {
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const locale = await currentLocale();
  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={['Supervisión', 'Documentación']}
        title={locale === 'es-PE' ? 'Documentación' : 'Documentation'}
        subtitle={
          locale === 'es-PE'
            ? 'Material de referencia para la SBS y para los integradores de instituciones financieras.'
            : 'Reference material for SBS staff and financial-institution integrators.'
        }
      />
      <div className="mx-auto w-full max-w-7xl px-6 py-4">
        <DocsTabs locale={locale} />
      </div>
    </main>
  );
}
