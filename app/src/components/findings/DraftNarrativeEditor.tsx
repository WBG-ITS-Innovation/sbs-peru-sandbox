// SPDX-License-Identifier: Apache-2.0
// Draft narrative editor. Client component — controlled textarea, save
// button POSTs to /app/api/findings/:id/draft (Next.js proxy) which
// forwards to /v1/internal/findings/:id/draft. The backend writes a
// complaint_narrative_drafts row + an audit_events row.

'use client';

import { useState, useTransition } from 'react';

import { Button, Card, CardBody, CardFooter, CardHeader, CardTitle } from '@/components/ui';
import { cn } from '@/lib/cn';

interface DraftNarrativeEditorProps {
  complaintId: string;
  initialText: string;
  agentDraftedText: string | null;
  csrfToken: string;
  actorId: string;
  agentRunId: string | null;
  labels: {
    title: string;
    save: string;
    edit: string;
    cancel: string;
    agent_drafted: string;
    no_edits_yet: string;
  };
}

export function DraftNarrativeEditor({
  complaintId,
  initialText,
  agentDraftedText,
  csrfToken,
  actorId,
  agentRunId,
  labels,
}: DraftNarrativeEditorProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [text, setText] = useState(initialText);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const dirty = text !== initialText;

  function save() {
    if (!dirty) return;
    startTransition(async () => {
      setError(null);
      const response = await fetch(
        `/app/api/findings/${encodeURIComponent(complaintId)}/draft`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-SBS-CSRF': csrfToken,
          },
          credentials: 'include',
          body: JSON.stringify({
            after_text: text,
            actor_id: actorId,
            agent_run_id: agentRunId,
          }),
        },
      );
      if (!response.ok) {
        setError(`HTTP ${response.status}`);
        return;
      }
      const body = await response.json();
      setSavedAt(body.created_at);
      setIsEditing(false);
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{labels.title}</CardTitle>
        {agentDraftedText ? (
          <p className="text-2xs text-fg-muted">{labels.agent_drafted}</p>
        ) : null}
      </CardHeader>
      <CardBody>
        {isEditing ? (
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            rows={6}
            className={cn(
              'block w-full rounded-sbs border border-border bg-surface px-3 py-2 text-sm text-fg',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2',
            )}
          />
        ) : (
          <p className="whitespace-pre-wrap rounded-sbs border border-border-subtle bg-surface-subtle p-3 text-sm text-fg">
            {text || <span className="text-fg-muted">{labels.no_edits_yet}</span>}
          </p>
        )}
        {savedAt ? (
          // Glyph + an already-localised timestamp — no translatable copy.
          // eslint-disable-next-line i18next/no-literal-string
          <p className="mt-2 text-2xs text-severity-low-fg">✓ {savedAt}</p>
        ) : null}
        {error ? (
          <p role="alert" className="mt-2 text-2xs text-severity-high-fg">
            {error}
          </p>
        ) : null}
      </CardBody>
      <CardFooter>
        {isEditing ? (
          <>
            <Button size="sm" onClick={save} disabled={!dirty || isPending}>
              {labels.save}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setText(initialText);
                setIsEditing(false);
              }}
              disabled={isPending}
            >
              {labels.cancel}
            </Button>
          </>
        ) : (
          <Button size="sm" variant="outline" onClick={() => setIsEditing(true)}>
            {labels.edit}
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}
