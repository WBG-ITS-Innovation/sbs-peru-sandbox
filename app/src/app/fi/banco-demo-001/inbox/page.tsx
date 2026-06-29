// SPDX-License-Identifier: Apache-2.0
import { FIInbox } from '@/components/fi/FIInbox';
import emails from '@/lib/journey-emails.json';
import golden from '@/lib/golden-complaint.json';

// FI app — Bandeja de reclamos. Server component reads the pre-extracted
// XLSX fixture and the golden-complaint pointer, hands both to the
// client which renders progressive arrival + recommended-demo badge.

export const dynamic = 'force-dynamic';

export default function FIInboxPage() {
  return (
    <FIInbox
      emails={emails as unknown as Array<Record<string, unknown>>}
      goldenComplaintId={golden.complaint_id}
    />
  );
}
