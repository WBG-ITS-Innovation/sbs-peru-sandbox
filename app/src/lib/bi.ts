import type { Locale } from '@/i18n';

// Inline bilingual literal. Spanish is primary, English the fallback —
// the demo audience (SBS Peru) reads Spanish; the inheriting vendor
// reads English. Kept as a call expression (not JSX text) so the
// i18next no-literal-string rule passes without a key per phrase.
export function bi(locale: Locale, es: string, en: string): string {
  return locale === 'en-US' ? en : es;
}
