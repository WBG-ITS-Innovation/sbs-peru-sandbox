// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { DemoJourneySbs } from '@/components/demo-journey/DemoJourneySbs';
import { currentLocale } from '@/i18n/server';
import golden from '@/lib/golden-complaint.json';

// SBS-side demo journey. Defaults to the golden complaint if no
// ?complaint_id= is supplied (so the supervisor can land here from the
// sidebar and still get a populated demo). When the FI app submits a
// new complaint, the FI submit page redirects to this route with the
// freshly minted complaint_id and the page polls /v1/audit + reads
// /v1/findings against that id.

export const dynamic = 'force-dynamic';

interface Props {
  searchParams?: Promise<{ complaint_id?: string }>;
}

export default async function DemoJourneyPage(props: Props) {
  const searchParams = await props.searchParams;
  const sessionId = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const locale = await currentLocale();
  const complaintId = searchParams?.complaint_id || golden.complaint_id;
  return <DemoJourneySbs locale={locale} complaintId={complaintId} />;
}
