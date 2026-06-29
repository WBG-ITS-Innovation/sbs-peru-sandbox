// SPDX-License-Identifier: Apache-2.0
// Server action: write the sbs-locale cookie so server components see
// the new locale on next render. Called from the LanguageToggle client
// component via a transition so the UI doesn't block on the round-trip.

'use server';

import { cookies } from 'next/headers';
import { revalidatePath } from 'next/cache';

import { LOCALE_COOKIE, localeCookieOptions } from '@/auth/cookies';
import { LOCALES, type Locale } from '@/i18n';

export async function setLocaleAction(locale: Locale): Promise<void> {
  if (!LOCALES.includes(locale)) {
    throw new Error(`Unknown locale: ${locale}`);
  }
  cookies().set(LOCALE_COOKIE, locale, localeCookieOptions());
  // Invalidate the current route so the language change is reflected
  // server-side.
  revalidatePath('/', 'layout');
}
