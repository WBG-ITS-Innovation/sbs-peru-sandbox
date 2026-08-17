// SPDX-License-Identifier: Apache-2.0
// Audit nested layout — adds the footer per the WS4 directive. The
// audit screen is the only place the WBG attribution renders; everywhere
// else the supervisor layout owns the chrome and the footer is omitted.

import { Footer } from '@/components/shell/Footer';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

export default function AuditLayout({ children }: { children: React.ReactNode }) {
  const locale = currentLocale();
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex-1 overflow-auto">{children}</div>
      <Footer attribution={t(locale, 'common.delivered_by')} />
    </div>
  );
}
