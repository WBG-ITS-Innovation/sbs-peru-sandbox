// i18n lookup — see ./README.md for namespace taxonomy and conventions.
// Pure module: usable from both server and client components. Locale
// resolution from the request cookie lives in ./server.ts because that
// imports next/headers and so must not leak into the client bundle.

import enDict from './en.json';
import esDict from './es.json';

export type Locale = 'es-PE' | 'en-US';

export const DEFAULT_LOCALE: Locale = 'es-PE';

export const LOCALES: readonly Locale[] = ['es-PE', 'en-US'] as const;

const dictionaries: Record<Locale, unknown> = {
  'es-PE': esDict,
  'en-US': enDict,
};

/**
 * Look up a dotted-path key against the dictionary for `locale`. Returns
 * the localized string, or — in non-production builds — logs a warning
 * and returns the key itself so missing strings are visible (not blank).
 */
export function t(locale: Locale, key: string): string {
  const value = key.split('.').reduce<unknown>((acc, segment) => {
    if (acc && typeof acc === 'object' && segment in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[segment];
    }
    return undefined;
  }, dictionaries[locale]);

  if (typeof value !== 'string') {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.warn(`i18n: missing or non-string key "${key}" for locale "${locale}"`);
    }
    return key;
  }
  return value;
}
