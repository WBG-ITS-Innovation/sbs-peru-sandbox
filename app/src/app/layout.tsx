import type { Metadata } from 'next';

import { currentLocale } from '@/i18n/server';

import './globals.css';

// `metadata` is evaluated at build time; the literal "SBS SupTech" is
// the product name (carried in both dictionaries as common.app_name) and
// is intentionally locale-independent here. Per-screen titles land with
// their owning workstreams.
export const metadata: Metadata = {
  title: 'SBS SupTech',
  description: 'Supervisor UI for the SBS SupTech prototype',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = currentLocale();
  return (
    <html lang={locale}>
      <body>{children}</body>
    </html>
  );
}
