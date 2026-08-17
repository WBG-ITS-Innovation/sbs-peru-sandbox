// SPDX-License-Identifier: Apache-2.0
// Server-only helpers — keep this file out of client components so the
// `next/headers` import never lands in the client bundle.

import 'server-only';

import { cookies } from 'next/headers';

import { DEFAULT_LOCALE, LOCALES, type Locale } from './index';

export const LOCALE_COOKIE = 'sbs-locale';

/**
 * Resolve the active locale for the current request. Reads the
 * `sbs-locale` cookie and falls back to `es-PE`. The language toggle in
 * the top bar (lands with the OAuth commit) writes this cookie via a
 * server action.
 */
export async function currentLocale(): Promise<Locale> {
  const value = (await cookies()).get(LOCALE_COOKIE)?.value;
  if (value && LOCALES.includes(value as Locale)) {
    return value as Locale;
  }
  return DEFAULT_LOCALE;
}
