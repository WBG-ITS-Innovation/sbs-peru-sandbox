import type { Metadata } from 'next';
import { IBM_Plex_Mono, Inter } from 'next/font/google';

import { currentLocale } from '@/i18n/server';

import './globals.css';

// ADR 0041 D1 — Inter as the UI typeface, IBM Plex Mono for monospace.
// `next/font/google` self-hosts (no third-party CDN at runtime) and
// produces a CSS custom property our Tailwind config consumes.
const inter = Inter({
  subsets: ['latin', 'latin-ext'],
  variable: '--font-sans',
  display: 'swap',
});

const ibmPlexMono = IBM_Plex_Mono({
  weight: ['400', '500', '700'],
  subsets: ['latin'],
  variable: '--font-mono',
  display: 'swap',
});

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
    <html lang={locale} className={`${inter.variable} ${ibmPlexMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
