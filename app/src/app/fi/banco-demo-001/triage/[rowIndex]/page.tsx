// SPDX-License-Identifier: Apache-2.0
import { notFound } from 'next/navigation';

import { FITriage } from '@/components/fi/FITriage';
import emails from '@/lib/journey-emails.json';

export const dynamic = 'force-dynamic';

interface Props {
  params: Promise<{ rowIndex: string }>;
}

export default async function FITriagePage(props: Props) {
  const params = await props.params;
  const idx = Number.parseInt(params.rowIndex, 10);
  const rows = emails as unknown as Array<Record<string, unknown>>;
  if (Number.isNaN(idx) || idx < 0 || idx >= rows.length) {
    notFound();
  }
  return <FITriage row={rows[idx]} rowIndex={idx} />;
}
