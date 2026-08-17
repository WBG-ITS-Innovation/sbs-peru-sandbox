// SPDX-License-Identifier: Apache-2.0
import {
  AlertTriangle,
  Book,
  FileCode,
  Info,
  Play,
  Radio,
  Rocket,
  Shield,
} from 'lucide-react';

import Link from 'next/link';

import { LiveApiPanel } from '@/components/developers/LiveApiPanel';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card, CardBody, CardHeader, CardTitle } from '@/components/ui/Card';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

// /app/developers — integrator-facing landing page. No backend calls;
// every working button is disabled and labelled "Vista previa · no
// conectado al flujo operativo actual" so an institution opening the
// page understands the surface is documentation, not a live onboarding
// console.

export const dynamic = 'force-dynamic';

export default function DevelopersPortalPage() {
  const locale = currentLocale();
  const tr = (key: string) => t(locale, key);

  const previewDisclaimer = tr('pilot.preview_disclaimer');
  const pilotBadge = tr('pilot.badge');
  const previewOnly = tr('developers.portal.status_disclaimer');

  const capabilities = [
    {
      icon: Rocket,
      title: tr('developers.portal.capabilities.quickstart_title'),
      body: tr('developers.portal.capabilities.quickstart_body'),
    },
    {
      icon: Shield,
      title: tr('developers.portal.capabilities.auth_title'),
      body: tr('developers.portal.capabilities.auth_body'),
    },
    {
      icon: FileCode,
      title: tr('developers.portal.capabilities.schemas_title'),
      body: tr('developers.portal.capabilities.schemas_body'),
    },
    {
      icon: Radio,
      title: tr('developers.portal.capabilities.webhooks_title'),
      body: tr('developers.portal.capabilities.webhooks_body'),
    },
  ];

  const cadences = [
    {
      title: tr('developers.portal.cadence.nrt_title'),
      audience: tr('developers.portal.cadence.nrt_audience'),
      sla: tr('developers.portal.cadence.nrt_sla'),
      endpoint: tr('developers.portal.cadence.nrt_endpoint'),
    },
    {
      title: tr('developers.portal.cadence.daily_title'),
      audience: tr('developers.portal.cadence.daily_audience'),
      sla: tr('developers.portal.cadence.daily_sla'),
      endpoint: tr('developers.portal.cadence.daily_endpoint'),
    },
    {
      title: tr('developers.portal.cadence.weekly_monthly_title'),
      audience: tr('developers.portal.cadence.weekly_monthly_audience'),
      sla: tr('developers.portal.cadence.weekly_monthly_sla'),
      endpoint: tr('developers.portal.cadence.weekly_monthly_endpoint'),
    },
    {
      title: tr('developers.portal.cadence.quarterly_title'),
      audience: tr('developers.portal.cadence.quarterly_audience'),
      sla: tr('developers.portal.cadence.quarterly_sla'),
      endpoint: tr('developers.portal.cadence.quarterly_endpoint'),
    },
  ];

  const resources = [
    { icon: Book, label: tr('developers.portal.resources.guide') },
    { icon: FileCode, label: tr('developers.portal.resources.catalog') },
    { icon: Shield, label: tr('developers.portal.resources.pii') },
    { icon: AlertTriangle, label: tr('developers.portal.resources.errors') },
  ];

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <section className="rounded-sbs border border-border bg-surface-subtle p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="max-w-3xl">
            <Badge variant="source" className="mb-2">
              {tr('developers.credentials.table.tier1_chip')}
            </Badge>
            <h2 className="font-serif text-2xl font-semibold tracking-tight text-fg">
              {tr('developers.portal.hero_title')}
            </h2>
            <p className="mt-1 text-sm text-fg-muted">
              {tr('developers.portal.hero_subtitle')}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button variant="default" size="sm" disabled aria-disabled="true">
                <Rocket className="h-3.5 w-3.5" aria-hidden="true" />
                {tr('developers.portal.start_integration')}
              </Button>
              <Link
                href="/sandbox"
                className="inline-flex items-center gap-1.5 rounded-sbs border border-brand-navy bg-brand-navy px-3 py-1.5 text-xs font-medium text-fg-inverted hover:bg-brand-navy/90"
              >
                <Play className="h-3.5 w-3.5" aria-hidden="true" />
                {tr('developers.portal.try_sandbox')}
              </Link>
            </div>
          </div>
          <Badge variant="role" className="border-brand-gold/40 bg-brand-gold/10 text-brand-navy">
            {pilotBadge}
          </Badge>
        </div>
        <div
          role="status"
          className="mt-4 flex items-center gap-2 rounded-sbs border border-border bg-surface px-3 py-2 text-xs text-fg-muted"
        >
          <Info className="h-3.5 w-3.5 text-brand-gold" aria-hidden="true" />
          <span>{previewDisclaimer}</span>
        </div>
      </section>

      <LiveApiPanel locale={locale} />

      <section>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {capabilities.map(c => (
            <Card key={c.title}>
              <CardBody>
                <c.icon className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
                <p className="mt-2 text-sm font-semibold text-fg">{c.title}</p>
                <p className="mt-1 text-xs text-fg-muted">{c.body}</p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-serif text-xl font-semibold tracking-tight text-fg">
            {tr('developers.portal.cadence_title')}
          </h3>
          <p className="font-mono text-2xs uppercase tracking-wider text-fg-muted">
            {tr('developers.portal.cadence_subtitle')}
          </p>
        </header>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {cadences.map(c => (
            <Card key={c.title} className="border-border">
              <CardHeader className="border-b border-border px-4 py-2.5">
                <CardTitle className="font-mono text-2xs font-semibold uppercase tracking-wider text-brand-navy">
                  {c.title}
                </CardTitle>
              </CardHeader>
              <CardBody className="px-4 py-3">
                <p className="text-xs text-fg">{c.audience}</p>
                <dl className="mt-3 space-y-1.5 text-2xs text-fg-muted">
                  <div className="flex justify-between gap-2">
                    <dt className="font-mono uppercase tracking-wider">
                      {tr('developers.credentials.table.sla_label')}
                    </dt>
                    <dd className="font-mono tabular text-fg">{c.sla}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="font-mono uppercase tracking-wider">
                      {tr('developers.credentials.table.endpoint_label')}
                    </dt>
                    <dd className="font-mono tabular text-fg">{c.endpoint}</dd>
                  </div>
                </dl>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <header className="mb-3 flex items-baseline justify-between">
          <h3 className="text-base font-semibold tracking-tight text-fg">
            {tr('developers.portal.resources_title')}
          </h3>
        </header>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {resources.map(r => (
            <Card key={r.label}>
              <CardBody className="flex items-start gap-2">
                <r.icon className="mt-0.5 h-4 w-4 text-brand-cyan" aria-hidden="true" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-fg">{r.label}</p>
                  <p className="mt-0.5 text-2xs text-fg-muted">{previewOnly}</p>
                </div>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">{tr('developers.portal.status_title')}</CardTitle>
          <p className="text-xs text-fg-muted">
            {tr('developers.portal.status_subtitle')}
          </p>
        </CardHeader>
        <CardBody>
          <p className="text-xs text-fg-muted">{previewOnly}</p>
        </CardBody>
      </Card>
    </main>
  );
}
