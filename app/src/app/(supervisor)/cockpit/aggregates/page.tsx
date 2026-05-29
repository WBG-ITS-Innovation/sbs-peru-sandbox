import { AggregateTables } from '@/components/persona/AggregateTables';
import { AggregatesView } from '@/components/persona/AggregatesView';
import { currentLocale } from '@/i18n/server';

// Aggregates & Agents tab (P-RESHAPE-RECOVERY-FINAL). Additive surface
// that renders the live worker output (patterns, agent status, sector
// broadcast) which already lands in the DB. The (supervisor) layout
// supplies the session guard, nav rail, and top bar.
//
// View 1 (AggregateTables) mounts ABOVE AggregatesView: real SQL-computed
// grouped aggregates from /v1/internal/aggregates/patterns, the truthful
// counterpart to the fabricated "Patterns & broadcasts" table below it.
export const dynamic = 'force-dynamic';

export default function AggregatesPage() {
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
