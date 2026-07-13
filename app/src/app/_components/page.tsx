// SPDX-License-Identifier: Apache-2.0
/* eslint-disable i18next/no-literal-string */
// ADR 0041 D4 — the component index. Every primitive in every variant
// on one screen so reviewers can scan Badge:critical next to
// Button:destructive next to Toast:critical and catch any visual
// inconsistency immediately. Section labels route through i18n;
// in-demo literals (`Approve`, `Critical`, sample numbers) are
// deliberately hardcoded — this page is a developer-facing reference
// and translating "Default variant" would add noise without value.

import { AlertTriangle, FileText, Filter, Inbox, Search } from 'lucide-react';

import {
  Badge,
  Button,
  Card,
  CardBody,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  EmptyState,
  ErrorBoundary,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
  Skeleton,
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui';
import { t } from '@/i18n';
import { currentLocale } from '@/i18n/server';

import { ToastsDemo } from './toasts-demo';
import { ErrorBoundaryDemo } from './error-boundary-demo';

const RESERVED_PRIMITIVES = [
  { name: 'Radio', reason: 'Findings filters use Select; no use case before WS6.' },
  { name: 'Textarea', reason: 'Approvals rationale uses styled native textarea inline.' },
  { name: 'Popover', reason: 'Tooltip covers the "why this fired" affordance.' },
  { name: 'Toggle', reason: 'Language switch uses Select; no toggle use case before WS3.' },
];

export default function ComponentIndexPage() {
  const locale = currentLocale();
  const section = (key: string): string => t(locale, `components_index.sections.${key}`);

  return (
    <TooltipProvider>
      <main className="mx-auto max-w-5xl space-y-12 p-8">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold text-fg">
            {t(locale, 'components_index.title')}
          </h1>
          <p className="text-sm text-fg-muted">
            {t(locale, 'components_index.subtitle')}
          </p>
        </header>

        <section aria-labelledby="buttons" className="space-y-3">
          <h2 id="buttons" className="text-xl font-semibold text-fg">{section('buttons')}</h2>
          <div className="flex flex-wrap gap-3">
            <Button variant="default">Aprobar</Button>
            <Button variant="secondary">Devolver</Button>
            <Button variant="outline">Editar</Button>
            <Button variant="ghost">Cancelar</Button>
            <Button variant="link">Ver detalles</Button>
            <Button variant="destructive">Rechazar</Button>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm">Small</Button>
            <Button size="md">Medium</Button>
            <Button size="lg">Large</Button>
            <Button disabled>Disabled</Button>
          </div>
        </section>

        <section aria-labelledby="inputs" className="space-y-3">
          <h2 id="inputs" className="text-xl font-semibold text-fg">{section('inputs')}</h2>
          <div className="grid max-w-md gap-3">
            <Input placeholder="Buscar institución..." />
            <Input placeholder="Disabled" disabled />
            <Input type="search" placeholder="Search" />
          </div>
        </section>

        <section aria-labelledby="selects" className="space-y-3">
          <h2 id="selects" className="text-xl font-semibold text-fg">{section('selects')}</h2>
          <div className="max-w-xs">
            <Select>
              <SelectTrigger>
                <SelectValue placeholder="Severidad" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">Baja</SelectItem>
                <SelectItem value="medium">Media</SelectItem>
                <SelectItem value="high">Alta</SelectItem>
                <SelectItem value="critical">Crítica</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </section>

        <section aria-labelledby="checkboxes" className="space-y-3">
          <h2 id="checkboxes" className="text-xl font-semibold text-fg">{section('checkboxes')}</h2>
          <div className="flex items-center gap-2">
            <Checkbox id="cb-1" defaultChecked />
            <label htmlFor="cb-1" className="text-sm text-fg">Filtrar Tier 1</label>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="cb-2" />
            <label htmlFor="cb-2" className="text-sm text-fg">Filtrar Tier 2</label>
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="cb-3" disabled />
            <label htmlFor="cb-3" className="text-sm text-fg-subtle">Deshabilitado</label>
          </div>
        </section>

        <section aria-labelledby="badges" className="space-y-3">
          <h2 id="badges" className="text-xl font-semibold text-fg">{section('badges')}</h2>
          <div className="flex flex-wrap gap-2">
            <Badge variant="low">Baja</Badge>
            <Badge variant="medium">Media</Badge>
            <Badge variant="high">Alta</Badge>
            <Badge variant="critical">Crítica</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="pending">Pendiente</Badge>
            <Badge variant="in-review">En revisión</Badge>
            <Badge variant="resolved">Resuelto</Badge>
            <Badge variant="escalated">Escalado</Badge>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="source">Tier 1 · API</Badge>
            <Badge variant="source">Tier 2 · Batch</Badge>
            <Badge variant="role">Supervisor · Supervisora</Badge>
            <Badge variant="role">Head · Jefe</Badge>
          </div>
        </section>

        <section aria-labelledby="cards" className="space-y-3">
          <h2 id="cards" className="text-xl font-semibold text-fg">{section('cards')}</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>BANCO_DEMO_001</CardTitle>
                <CardDescription>Tier 1 · Last 24 hours</CardDescription>
              </CardHeader>
              <CardBody>
                <p className="tabular text-3xl font-semibold text-fg">412</p>
                <p className="text-xs text-fg-muted">complaints received</p>
              </CardBody>
              <CardFooter>
                <Badge variant="high">Velocity high</Badge>
              </CardFooter>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>COOPAC_DEMO_002</CardTitle>
                <CardDescription>Tier 2 · Last 28 days</CardDescription>
              </CardHeader>
              <CardBody>
                <p className="tabular text-3xl font-semibold text-fg">67</p>
                <p className="text-xs text-fg-muted">complaints processed</p>
              </CardBody>
              <CardFooter>
                <Badge variant="medium">Severity median</Badge>
              </CardFooter>
            </Card>
          </div>
        </section>

        <section aria-labelledby="tables" className="space-y-3">
          <h2 id="tables" className="text-xl font-semibold text-fg">{section('tables')}</h2>
          <Table>
            <TableHeader>
              <tr>
                <TableHead>Complaint</TableHead>
                <TableHead>Institution</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
              </tr>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="font-mono text-xs">BCO-2026-000001</TableCell>
                <TableCell>BANCO_DEMO_001</TableCell>
                <TableCell><Badge variant="high">Alta</Badge></TableCell>
                <TableCell className="tabular text-right">0.87</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-mono text-xs">BCO-2026-000002</TableCell>
                <TableCell>BANCO_DEMO_001</TableCell>
                <TableCell><Badge variant="medium">Media</Badge></TableCell>
                <TableCell className="tabular text-right">0.62</TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="font-mono text-xs">BCO-2026-000003</TableCell>
                <TableCell>COOPAC_DEMO_002</TableCell>
                <TableCell><Badge variant="critical">Crítica</Badge></TableCell>
                <TableCell className="tabular text-right">0.94</TableCell>
              </TableRow>
            </TableBody>
            <TableCaption>{t(locale, 'components_index.demo.table_caption')}</TableCaption>
          </Table>
        </section>

        <section aria-labelledby="dialogs" className="space-y-3">
          <h2 id="dialogs" className="text-xl font-semibold text-fg">{section('dialogs')}</h2>
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="outline">Abrir diálogo</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Confirmar rechazo</DialogTitle>
                <DialogDescription>
                  Este hallazgo será devuelto al analista con la justificación
                  proporcionada. Esta acción no puede deshacerse.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline">Cancelar</Button>
                <Button variant="destructive">Rechazar</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </section>

        <section aria-labelledby="sheets" className="space-y-3">
          <h2 id="sheets" className="text-xl font-semibold text-fg">{section('sheets')}</h2>
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline">Abrir panel</Button>
            </SheetTrigger>
            <SheetContent side="right">
              <SheetTitle>Detalles del hallazgo</SheetTitle>
              <SheetDescription>
                Panel lateral para el contexto del agente: razonamiento,
                evidencia y la cadena de auditoría.
              </SheetDescription>
            </SheetContent>
          </Sheet>
        </section>

        <section aria-labelledby="toasts" className="space-y-3">
          <h2 id="toasts" className="text-xl font-semibold text-fg">{section('toasts')}</h2>
          <ToastsDemo />
        </section>

        <section aria-labelledby="tooltips" className="space-y-3">
          <h2 id="tooltips" className="text-xl font-semibold text-fg">{section('tooltips')}</h2>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="outline" size="sm" aria-label="why this fired">
                <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Anomaly fired because composite signal velocity crossed 0.7
              (INDECOPI 0.30 + sentiment 0.20 + narrative 0.25).
            </TooltipContent>
          </Tooltip>
        </section>

        <section aria-labelledby="skeletons" className="space-y-3">
          <h2 id="skeletons" className="text-xl font-semibold text-fg">{section('skeletons')}</h2>
          <div className="space-y-2">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        </section>

        <section aria-labelledby="empty_states" className="space-y-3">
          <h2 id="empty_states" className="text-xl font-semibold text-fg">{section('empty_states')}</h2>
          <EmptyState
            icon={<Inbox className="h-6 w-6" aria-hidden="true" />}
            title="No pending approvals"
            body="Head has cleared the queue. New findings will land here when analysts send them up."
            primaryAction={{ label: 'Open Risk Queue', href: '/queue' }}
            secondaryLink={{ label: 'Read approvals workflow docs', href: '/audit' }}
          />
          <EmptyState
            icon={<Filter className="h-6 w-6" aria-hidden="true" />}
            title="No findings match these filters"
            body="The current filter set returns no rows. Clear the filters to widen the search, or open the Tier 1 ingestion documentation if you expected data here."
            primaryAction={{ label: 'Clear filters', href: '/findings' }}
            secondaryLink={{ label: 'Tier 1 ingestion docs', href: '/audit' }}
          />
          <EmptyState
            icon={<Search className="h-6 w-6" aria-hidden="true" />}
            title="No audit entries match"
            body="No state-changing actions match the actor / action / object filter. Audit retention is currently the demo window (last 72 hours)."
            primaryAction={{ label: 'Reset search', href: '/audit' }}
          />
        </section>

        <section aria-labelledby="error_boundaries" className="space-y-3">
          <h2 id="error_boundaries" className="text-xl font-semibold text-fg">{section('error_boundaries')}</h2>
          <ErrorBoundaryDemo />
        </section>

        <section aria-labelledby="reserved" className="space-y-3 border-t border-border pt-8">
          <h2 id="reserved" className="text-xl font-semibold text-fg">
            {t(locale, 'components_index.reserved')}
          </h2>
          <p className="text-sm text-fg-muted">
            {t(locale, 'components_index.reserved_body')}
          </p>
          <ul className="space-y-1 text-sm text-fg">
            {RESERVED_PRIMITIVES.map(p => (
              <li key={p.name} className="flex items-baseline gap-2">
                <Badge variant="default">
                  <FileText className="h-3 w-3" aria-hidden="true" />
                  <span>{p.name}</span>
                </Badge>
                <span className="text-fg-muted">— {p.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </TooltipProvider>
  );
}
