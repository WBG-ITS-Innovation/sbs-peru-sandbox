import { redirect } from 'next/navigation';

import { activePersona } from '@/auth/persona-server';
import { AnalystDashboard } from '@/components/persona/dashboards/AnalystDashboard';
import { SbsItDashboard } from '@/components/persona/dashboards/SbsItDashboard';
import { SuperintendentDashboard } from '@/components/persona/dashboards/SuperintendentDashboard';
import { SupervisorDashboard } from '@/components/persona/dashboards/SupervisorDashboard';
import { UnitHeadDashboard } from '@/components/persona/dashboards/UnitHeadDashboard';
import { currentLocale } from '@/i18n/server';
import { isPersonaSlug } from '@/lib/persona';

export const dynamic = 'force-dynamic';

// Persona scoping is authoritative here: the active persona comes from
// the cookie, never the URL. Reaching another persona's URL redirects to
// your own dashboard, and every data fetch downstream is scoped to the
// cookie persona's role — so a caller cannot widen their view by editing
// the path. (Smoke step 8: Sergio → /dashboard/conduct_analyst redirects.)
export default function PersonaDashboardPage({
  params,
}: {
  params: { persona: string };
}) {
  const active = activePersona();
  if (!active) {
    redirect('/login');
  }
  if (!isPersonaSlug(params.persona) || params.persona !== active.slug) {
    redirect(`/dashboard/${active.slug}`);
  }

  const locale = currentLocale();

  switch (active.slug) {
    case 'conduct_analyst':
      return <AnalystDashboard persona={active} locale={locale} />;
    case 'conduct_supervisor':
      return <SupervisorDashboard persona={active} locale={locale} />;
    case 'conduct_unit_head':
      return <UnitHeadDashboard persona={active} locale={locale} />;
    case 'superintendent':
      return <SuperintendentDashboard persona={active} locale={locale} />;
    case 'sbs_it':
      return <SbsItDashboard persona={active} locale={locale} />;
    default:
      redirect('/login');
  }
}
