// SPDX-License-Identifier: Apache-2.0
import { ListChecks } from 'lucide-react';

import { EmptyState } from '@/components/ui';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Risk Queue — stubbed for the May 25 demo per the drop ladder. The
// nav rail link works; the route doesn't fight. Filtering against the
// complaints table is available on the Findings screen until the
// queue's bulk-assign affordance lands in a follow-up.
export default function QueuePage() {
  const locale = currentLocale();
  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-4 text-2xl font-semibold text-fg">{t(locale, 'queue.title')}</h1>
      <EmptyState
        icon={<ListChecks className="h-6 w-6" aria-hidden="true" />}
        title={t(locale, 'queue.deferred.title')}
        body={t(locale, 'queue.deferred.body')}
        primaryAction={{
          label: t(locale, 'queue.deferred.primary'),
          href: '/findings',
        }}
      />
    </main>
  );
}
