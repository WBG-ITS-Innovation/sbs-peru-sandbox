import type { Metadata } from 'next';

import './globals.css';

// Branding text and locale are intentionally placeholder values; the i18n
// contract (next commit) replaces these with translated strings. They are
// not user-facing surface yet — the empty placeholder pages render before
// WS1 styles them.
export const metadata: Metadata = {
  title: 'SBS SupTech',
  description: 'Supervisor UI for the SBS SupTech prototype',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es-PE">
      <body>{children}</body>
    </html>
  );
}
