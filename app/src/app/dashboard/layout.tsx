import { activePersona } from '@/auth/persona-server';
import { SwitchPersona } from '@/components/persona/SwitchPersona';
import { LanguageToggle } from '@/components/shell/LanguageToggle';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';
import { bi } from '@/lib/bi';
import { personaTitle } from '@/lib/persona';

export const dynamic = 'force-dynamic';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const locale = currentLocale();
  const persona = activePersona();

  return (
    <div className="flex min-h-screen flex-col bg-surface-subtle">
      <header className="flex items-center justify-between border-b border-border bg-brand-navy px-4 py-2 text-fg-inverted">
        <div className="flex items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/app/sbs-logo.png" alt="SBS" className="h-7 w-auto" />
          <span className="font-mono text-2xs uppercase tracking-wider text-fg-inverted/70">
            {bi(locale, 'Cabina SupTech', 'SupTech Cockpit')}
          </span>
        </div>
        <div className="flex items-center gap-3">
          {persona ? (
            <span className="text-xs">
              <span className="font-semibold">{persona.name}</span>
              <span className="text-fg-inverted/70"> · {personaTitle(persona, locale)}</span>
            </span>
          ) : null}
          <LanguageToggle
            currentLocale={locale}
            labels={{
              es: t(locale, 'common.locale.es-PE'),
              en: t(locale, 'common.locale.en-US'),
              toggle: t(locale, 'nav.language_toggle'),
            }}
          />
          <SwitchPersona locale={locale} />
        </div>
      </header>
      <main className="flex-1">{children}</main>
    </div>
  );
}
