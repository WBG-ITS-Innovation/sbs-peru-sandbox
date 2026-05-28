'use client';

import { useState, useTransition } from 'react';

import {
  ackTaskAction,
  completeTaskAction,
  declineTaskAction,
} from '@/app/dashboard/actions';
import { Badge, Button } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import type { TaskItem } from '@/types/persona-dashboards';

const DECLINE_MIN = 30; // backend enforces rationale ≥ 30 chars on decline.

function TaskMeta({ task }: { task: TaskItem }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge variant="role">{task.task_type}</Badge>
      <span className="font-mono text-2xs text-fg-subtle">
        {task.ref_type}:{task.ref_id}
      </span>
      <Badge variant={task.state === 'OPEN' ? 'pending' : 'resolved'}>{task.state}</Badge>
    </div>
  );
}

function InboxRow({ task, locale }: { task: TaskItem; locale: Locale }) {
  const [pending, start] = useTransition();
  const [declining, setDeclining] = useState(false);
  const [rationale, setRationale] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  const done = task.state !== 'OPEN' && task.state !== 'ACKED';

  return (
    <li className="rounded-sbs border border-border bg-surface p-2.5">
      <TaskMeta task={task} />
      <p className="mt-1 text-xs text-fg">{task.rationale}</p>
      <p className="mt-0.5 text-2xs text-fg-subtle">
        {bi(locale, 'De', 'From')} {task.created_by_user_id}
      </p>

      {msg ? <p className="mt-1 text-2xs text-fg-muted">{msg}</p> : null}

      {!done && !declining ? (
        <div className="mt-2 flex gap-1.5">
          <Button
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() =>
              start(async () => {
                const r = await ackTaskAction(task.task_id);
                setMsg(`${r.ok ? bi(locale, 'Confirmada' , 'Acked') : bi(locale, 'Error', 'Error')} (${r.status})`);
              })
            }
          >
            {bi(locale, 'Confirmar', 'Acknowledge')}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={pending}
            onClick={() =>
              start(async () => {
                const r = await completeTaskAction(task.task_id);
                setMsg(`${r.ok ? bi(locale, 'Completada', 'Completed') : bi(locale, 'Error', 'Error')} (${r.status})`);
              })
            }
          >
            {bi(locale, 'Completar', 'Complete')}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setDeclining(true)}>
            {bi(locale, 'Rechazar', 'Decline')}
          </Button>
        </div>
      ) : null}

      {declining ? (
        <div className="mt-2 space-y-1.5">
          <textarea
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            rows={2}
            placeholder={bi(locale, 'Motivo del rechazo', 'Reason for declining')}
            className="w-full rounded-sbs border border-border bg-surface px-2 py-1 text-xs text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          />
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="destructive"
              disabled={pending || rationale.trim().length < DECLINE_MIN}
              onClick={() =>
                start(async () => {
                  const r = await declineTaskAction(task.task_id, rationale.trim());
                  setMsg(`${r.ok ? bi(locale, 'Rechazada', 'Declined') : bi(locale, 'Error', 'Error')} (${r.status})`);
                  if (r.ok) setDeclining(false);
                })
              }
            >
              {bi(locale, 'Confirmar rechazo', 'Confirm decline')}
            </Button>
            <span className="font-mono text-2xs text-fg-subtle">
              {rationale.trim().length}/{DECLINE_MIN}
            </span>
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function TaskInbox({ tasks, locale }: { tasks: TaskItem[]; locale: Locale }) {
  if (tasks.length === 0) {
    return (
      <p className="text-xs text-fg-muted">
        {bi(locale, 'Bandeja de entrada vacía.', 'Inbox empty.')}
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {tasks.map((t) => (
        <InboxRow key={t.task_id} task={t} locale={locale} />
      ))}
    </ul>
  );
}

export function TaskOutbox({ tasks, locale }: { tasks: TaskItem[]; locale: Locale }) {
  if (tasks.length === 0) {
    return (
      <p className="text-xs text-fg-muted">
        {bi(locale, 'Bandeja de salida vacía.', 'Outbox empty.')}
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {tasks.map((t) => (
        <li key={t.task_id} className="rounded-sbs border border-border bg-surface p-2.5">
          <TaskMeta task={t} />
          <p className="mt-1 text-xs text-fg">{t.rationale}</p>
          <p className="mt-0.5 text-2xs text-fg-subtle">
            {bi(locale, 'Para', 'To')} {t.assigned_to_user_id ?? t.assigned_to_persona}
          </p>
        </li>
      ))}
    </ul>
  );
}
