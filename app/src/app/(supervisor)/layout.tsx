import { redirect } from 'next/navigation';
import { cookies } from 'next/headers';

import { SESSION_COOKIE } from '@/auth/cookies';
import { authConfig } from '@/auth/config';
import { activePersona, getSession } from '@/auth/session';
import { NavRail } from '@/components/shell/NavRail';
import { TopBar } from '@/components/shell/TopBar';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// Supervisor route group layout. Wraps cockpit, queue, findings,
// approvals, audit. The audit screen adds the footer via its own
// nested layout — see (supervisor)/audit/layout.tsx.

export const dynamic = 'force-dynamic';

const ROLE_LABELS: Record<string, { es: string; en: string }> = {
  'sbs:conduct:supervisor': { es: 'Supervisora', en: 'Supervisor' },
  'sbs:conduct:analyst': { es: 'Analista', en: 'Analyst' },
  'sbs:conduct:head': { es: 'Jefe', en: 'Head' },
};

function resolveRoleLabel(roles: readonly string[], locale: 'es-PE' | 'en-US'): string {
  for (const role of roles) {
    const map = ROLE_LABELS[role];
    if (map) return locale === 'es-PE' ? map.es : map.en;
  }
  return '—';
}

function inferActivePersonaKey(
  demoMode: boolean,
  activeKey: string | null,
): 'maria' | 'lucia' | 'jorge' | null {
  if (!demoMode) return null;
  if (activeKey === 'maria' || activeKey === 'lucia' || activeKey === 'jorge') {
    return activeKey;
  }
  return null;
}

export default function SupervisorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const sessionId = cookies().get(SESSION_COOKIE)?.value;
  const session = getSession(sessionId);
  if (!session) {
    redirect('/login');
  }
  const persona = activePersona(session);
  const locale = currentLocale();

  const navLabels = {
    cockpit: t(locale, 'nav.cockpit'),
    findings: t(locale, 'nav.findings'),
    approvals: t(locale, 'nav.approvals'),
    audit: t(locale, 'nav.audit'),
    demo_journey: t(locale, 'nav.demo_journey'),
    ingestion: t(locale, 'nav.ingestion'),
    processing: t(locale, 'nav.processing'),
    rr1: t(locale, 'nav.rr1'),
    docs: t(locale, 'nav.docs'),
    analytics: t(locale, 'nav.analytics'),
    assistant: t(locale, 'nav.assistant'),
    pilot_phase: t(locale, 'nav.pilot_phase'),
    primary_label: t(locale, 'nav.primary_label'),
    role_indicator: t(locale, 'nav.role_indicator'),
  };

  const topBarLabels = {
    connectionLabel: {
      connecting: t(locale, 'cockpit.connection.connecting'),
      connected: t(locale, 'cockpit.connection.connected'),
      disconnected: t(locale, 'cockpit.connection.disconnected'),
    },
    languageToggle: {
      es: t(locale, 'common.locale.es-PE'),
      en: t(locale, 'common.locale.en-US'),
      toggle: t(locale, 'nav.language_toggle'),
    },
    persona: {
      switch_persona: t(locale, 'nav.switch_persona'),
      active_persona: t(locale, 'nav.active_persona'),
      maria: t(locale, 'personas.maria'),
      lucia: t(locale, 'personas.lucia'),
      jorge: t(locale, 'personas.jorge'),
      cancel: t(locale, 'common.actions.cancel'),
    },
  };

  return (
    <div className="flex h-screen min-h-0 w-full bg-surface">
      <NavRail labels={navLabels} roleLabel={resolveRoleLabel(persona.roles, locale)} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <TopBar
          lockup={t(locale, 'common.lockup')}
          locale={locale}
          demoMode={authConfig.demoMode && session.demoMode}
          activePersonaKey={inferActivePersonaKey(
            authConfig.demoMode && session.demoMode,
            session.activePersonaKey,
          )}
          csrfToken={session.csrfToken}
          labels={topBarLabels}
        />
        <div className="flex-1 overflow-auto">{children}</div>
      </div>
    </div>
  );
}
