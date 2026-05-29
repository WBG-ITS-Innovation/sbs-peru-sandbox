import { AggregatesView } from '@/components/persona/AggregatesView';
import { currentLocale } from '@/i18n/server';

// Aggregates & Agents tab (P-RESHAPE-RECOVERY-FINAL). Additive surface
// that renders the live worker output (patterns, agent status, sector
// broadcast) which already lands in the DB. The (supervisor) layout
// supplies the session guard, nav rail, and top bar.
export const dynamic = 'force-dynamic';

export default function AggregatesPage() {
  const locale = currentLocale();
  return <AggregatesView locale={locale} />;
}
