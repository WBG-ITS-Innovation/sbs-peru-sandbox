import { AggregatesWorkspace } from '@/components/persona/AggregatesWorkspace';
import { currentLocale } from '@/i18n/server';

// No-Keycloak fallback for the Aggregates view (cookie/stub demo path).
// Mirrors /app/cockpit/aggregates so the tab is reachable without SSO.
export const dynamic = 'force-dynamic';

export default function DashboardAggregatesPage() {
  const locale = currentLocale();
  return <AggregatesWorkspace locale={locale} />;
}
