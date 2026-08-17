// SPDX-License-Identifier: Apache-2.0
import { AggregatesWorkspace } from '@/components/persona/AggregatesWorkspace';
import { currentLocale } from '@/i18n/server';

// Aggregates surface — four top-level tabs (Tablas / Gráficos / Alertas
// rojas / Documentación) over the live-ingestion banner. The (supervisor)
// layout supplies the session guard, nav rail, and top bar.
export const dynamic = 'force-dynamic';

export default async function AggregatesPage() {
  const locale = await currentLocale();
  return <AggregatesWorkspace locale={locale} />;
}
