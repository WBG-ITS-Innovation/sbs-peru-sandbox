import { AggregateTables } from '@/components/persona/AggregateTables';
import { AggregatesView } from '@/components/persona/AggregatesView';
import { currentLocale } from '@/i18n/server';

// No-Keycloak fallback for the Aggregates & Agents view. The canonical
// route is /app/cockpit/aggregates (under the supervisor session). This
// additive twin renders the same view on the cookie/stub demo path, so
// the tab is reachable even when Keycloak SSO is unavailable. A static
// segment, so it takes precedence over /dashboard/[persona].
export const dynamic = 'force-dynamic';

export default function DashboardAggregatesPage() {
  const locale = currentLocale();
  return (
    <>
      <div className="mx-auto w-full max-w-screen-2xl p-4 pb-0">
        <AggregateTables locale={locale} />
      </div>
      <AggregatesView locale={locale} />
    </>
  );
}
