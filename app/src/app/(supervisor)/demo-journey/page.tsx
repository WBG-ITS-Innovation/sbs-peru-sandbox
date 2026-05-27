import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { DemoJourneyClient } from '@/components/demo-journey/DemoJourneyClient';
import { currentLocale } from '@/i18n/server';
import emails from '@/lib/journey-emails.json';

// Server component: gates on session, hands the pre-extracted XLSX rows
// to the client. The XLSX → JSON conversion runs offline via
// scripts/build_journey_fixtures.py; the page never touches openpyxl.

export const dynamic = 'force-dynamic';

export default function DemoJourneyPage() {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const locale = currentLocale();
  return (
    <DemoJourneyClient
      locale={locale}
      emails={emails as unknown as Array<Record<string, unknown>>}
      csrfToken={session.csrfToken}
    />
  );
}
