// SPDX-License-Identifier: Apache-2.0
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

import { SESSION_COOKIE } from '@/auth/cookies';
import { getSession } from '@/auth/session';
import { FISubmit } from '@/components/fi/FISubmit';
import emails from '@/lib/journey-emails.json';

export const dynamic = 'force-dynamic';

interface Props {
  params: { rowIndex: string };
}

export default function FISubmitPage({ params }: Props) {
  // Gated by session so the real signed POST through /app/api/journey/
  // submit picks up the supervisor's CSRF token; an anonymous browser
  // arriving here gets bounced to the SBS login.
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const idx = Number.parseInt(params.rowIndex, 10);
  const rows = emails as unknown as Array<Record<string, unknown>>;
  if (Number.isNaN(idx) || idx < 0 || idx >= rows.length) {
    redirect('/fi/banco-demo-001/inbox');
  }
  return <FISubmit row={rows[idx]} csrfToken={session.csrfToken} />;
}
