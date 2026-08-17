// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { RR1Workbench } from '@/components/rr1/RR1Workbench';
import { PageHeader } from '@/components/shell/PageHeader';
import { currentLocale } from '@/i18n/server';
import rr1 from '@/lib/rr1-2025.json';

// /app/rr1 — SUCAVE-style replicate of the RR1 reglamento de reclamos
// reporting. Three tabs (Empresa / Producto / Motivo) over a synthetic
// 2025 fixture — fictional institutions, generated volumes, built by
// scripts/build_rr1_fixture.py — plus a "build your own chart" panel
// with line, bar, heatmap, and stacked-area types.

export const dynamic = 'force-dynamic';

export default async function RR1Page() {
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const locale = await currentLocale();
  return (
    <main className="flex flex-col">
      <PageHeader
        breadcrumb={['Supervisión', 'RR1 · Reportes 2025']}
        title={locale === 'es-PE' ? 'RR1 · Reglamento de Reclamos · 2025' : 'RR1 · Complaints regulation · 2025'}
        subtitle={
          locale === 'es-PE'
            ? 'Replicación del reporte estadístico mensual SUCAVE. Tres dimensiones (Empresa, Producto, Motivo) sobre 12 meses. Construye visualizaciones a la carta abajo.'
            : 'Replica of the monthly SUCAVE statistical report. Three dimensions (Entity, Product, Motive) across 12 months. Build custom visualizations below.'
        }
      />
      <div className="mx-auto w-full max-w-7xl px-6 py-4">
        <RR1Workbench locale={locale} data={rr1 as unknown as RR1Data} />
      </div>
    </main>
  );
}

interface RR1Data {
  source: string;
  generated_at: string;
  sheets: Record<string, { label_col: string; months: string[]; rows: Array<{ label: string; values: Array<number | null>; total: number }> }>;
}
