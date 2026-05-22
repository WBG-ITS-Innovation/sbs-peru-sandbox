// Left navigation rail — five icon links + role indicator at bottom.
// Active state via usePathname so a deep link highlights correctly.

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  ClipboardList,
  FileText,
  History,
  ListChecks,
  type LucideIcon,
} from 'lucide-react';

import { cn } from '@/lib/cn';

interface NavItem {
  href: string;
  icon: LucideIcon;
  label: string;
}

interface NavRailProps {
  labels: {
    cockpit: string;
    queue: string;
    findings: string;
    approvals: string;
    audit: string;
    primary_label: string;
    role_indicator: string;
  };
  roleLabel: string;
}

export function NavRail({ labels, roleLabel }: NavRailProps) {
  const pathname = usePathname() ?? '';

  const items: NavItem[] = [
    { href: '/cockpit', icon: Activity, label: labels.cockpit },
    { href: '/queue', icon: ListChecks, label: labels.queue },
    { href: '/findings', icon: FileText, label: labels.findings },
    { href: '/approvals', icon: ClipboardList, label: labels.approvals },
    { href: '/audit', icon: History, label: labels.audit },
  ];

  return (
    <nav
      aria-label={labels.primary_label}
      className="flex h-full w-16 flex-col items-center justify-between border-r border-border bg-brand-navy py-3"
    >
      <div className="flex flex-col items-center gap-2">
        <div
          aria-label="SBS"
          className="mb-3 flex h-9 w-9 rotate-45 items-center justify-center rounded-sbs border border-brand-gold/60 bg-brand-navy text-sm font-bold text-brand-gold"
        >
          <span className="-rotate-45 tabular">S</span>
        </div>
        {items.map(({ href, icon: Icon, label }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              aria-label={label}
              aria-current={active ? 'page' : undefined}
              className={cn(
                'group relative flex h-10 w-10 items-center justify-center rounded-sbs text-fg-inverted/70',
                'hover:bg-brand-navy/60 hover:text-fg-inverted',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-brand-navy',
                active && 'bg-brand-cyan/20 text-brand-cyan',
              )}
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
              <span className="pointer-events-none absolute left-12 top-1/2 -translate-y-1/2 whitespace-nowrap rounded-sbs bg-brand-navy px-2 py-1 text-xs text-fg-inverted opacity-0 transition-opacity group-hover:opacity-100">
                {label}
              </span>
            </Link>
          );
        })}
      </div>

      <div
        aria-label={labels.role_indicator}
        className="flex flex-col items-center gap-1 px-1 text-center text-2xs uppercase tracking-wider text-fg-inverted/60"
      >
        <span className="rounded-sbs border border-brand-gold/40 bg-brand-navy px-1.5 py-0.5 text-brand-gold">
          {roleLabel}
        </span>
      </div>
    </nav>
  );
}
