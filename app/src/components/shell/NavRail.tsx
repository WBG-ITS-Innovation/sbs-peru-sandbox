// Left navigation rail. Top group is the real supervisor workflow
// (Cockpit, Findings, Approvals, Audit). A thin divider separates the
// pilot-phase preview screens (Analytics / Reports, Assistant) which
// render the FASE PILOTO badge inside.
//
// Active state via usePathname so a deep link highlights correctly.

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  BarChart3,
  BookOpen,
  ClipboardList,
  Cpu,
  FileText,
  History,
  Layers,
  LayoutGrid,
  Radio,
  Route,
  Send,
  Sparkles,
  type LucideIcon,
} from 'lucide-react';

import { cn } from '@/lib/cn';

interface NavItem {
  href: string;
  icon: LucideIcon;
  label: string;
  pilot?: boolean;
  alert?: boolean;
}

interface NavRailProps {
  labels: {
    cockpit: string;
    findings: string;
    approvals: string;
    audit: string;
    demo_journey: string;
    ingestion: string;
    processing: string;
    rr1: string;
    docs: string;
    analytics: string;
    assistant: string;
    pilot_phase: string;
    primary_label: string;
    role_indicator: string;
    aggregates?: string;
    sandbox?: string;
  };
  roleLabel: string;
}

export function NavRail({ labels, roleLabel }: NavRailProps) {
  const pathname = usePathname() ?? '';

  const primaryItems: NavItem[] = [
    { href: '/cockpit', icon: Activity, label: labels.cockpit },
    { href: '/ingestion', icon: Radio, label: labels.ingestion },
    { href: '/processing', icon: Cpu, label: labels.processing },
    { href: '/findings', icon: FileText, label: labels.findings },
    { href: '/approvals', icon: ClipboardList, label: labels.approvals },
    { href: '/audit', icon: History, label: labels.audit },
    { href: '/demo-journey', icon: Route, label: labels.demo_journey },
    { href: '/rr1', icon: LayoutGrid, label: labels.rr1 },
    { href: '/docs', icon: BookOpen, label: labels.docs },
    {
      href: '/cockpit/aggregates',
      icon: Layers,
      label: labels.aggregates ?? 'Agregados y Agentes',
      alert: true,
    },
    {
      href: '/sandbox',
      icon: Send,
      label: labels.sandbox ?? 'Simulador (Tier 1/2)',
    },
  ];
  const pilotItems: NavItem[] = [
    { href: '/analytics', icon: BarChart3, label: labels.analytics, pilot: true },
    { href: '/assistant', icon: Sparkles, label: labels.assistant, pilot: true },
  ];

  const renderItem = ({ href, icon: Icon, label, pilot, alert }: NavItem) => {
    const active = pathname === href || pathname.startsWith(`${href}/`);
    return (
      <Link
        key={href}
        href={href}
        aria-label={pilot ? `${label} — ${labels.pilot_phase}` : label}
        aria-current={active ? 'page' : undefined}
        className={cn(
          'group relative flex h-10 w-10 items-center justify-center rounded-sbs',
          // Inactive: full white icons read clearly on navy.
          'text-fg-inverted',
          'hover:bg-fg-inverted/10',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-brand-navy',
          // Active: clearly cyan, with a left rail accent for unambiguous
          // current-page indication.
          active &&
            'bg-brand-cyan/20 text-brand-cyan before:absolute before:left-[-12px] before:top-1 before:bottom-1 before:w-0.5 before:rounded-sbs before:bg-brand-cyan',
        )}
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
        {pilot ? (
          <span
            aria-hidden="true"
            className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full border border-brand-navy bg-brand-gold"
          />
        ) : null}
        {alert ? (
          <span
            aria-hidden="true"
            className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full border border-brand-navy bg-red-600"
          />
        ) : null}
        <span
          role="tooltip"
          className={cn(
            'pointer-events-none absolute left-12 top-1/2 z-10 -translate-y-1/2 whitespace-nowrap',
            'rounded-sbs border border-brand-gold/40 bg-brand-navy px-2 py-1 text-xs font-medium text-fg-inverted shadow-md',
            'opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100',
          )}
        >
          {label}
          {pilot ? (
            <span className="ml-1 font-mono text-brand-gold">
              · {labels.pilot_phase}
            </span>
          ) : null}
        </span>
      </Link>
    );
  };

  return (
    <nav
      aria-label={labels.primary_label}
      className="flex h-full w-16 flex-col items-center justify-between border-r border-border bg-brand-navy py-3"
    >
      <div className="flex flex-col items-center gap-2">
        {/* No diamond here — the top bar already carries the institutional
            brand mark. Avoid duplicate marks. */}
        {primaryItems.map(renderItem)}
        <div
          aria-hidden="true"
          className="my-2 h-px w-7 bg-brand-gold/30"
        />
        {pilotItems.map(renderItem)}
      </div>

      <div
        aria-label={labels.role_indicator}
        className="flex flex-col items-center gap-1 px-1 text-center font-mono text-2xs uppercase tracking-wider text-fg-inverted/70"
      >
        <span className="rounded-sbs border border-fg-inverted/25 bg-brand-navy px-1.5 py-0.5 font-medium text-fg-inverted/85">
          {roleLabel}
        </span>
      </div>
    </nav>
  );
}
