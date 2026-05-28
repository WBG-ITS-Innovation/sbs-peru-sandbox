'use client';

import { MessageSquare, X } from 'lucide-react';
import { useState, useTransition } from 'react';

import { sendChatAction } from '@/app/dashboard/actions';
import { Badge, Button } from '@/components/ui';
import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';
import type { ChatCitation, ChatMessage, ChatSession } from '@/types/persona-dashboards';

interface PanelProps {
  locale: Locale;
  initialSession: ChatSession | null;
  suggestedQuestions: string[];
}

interface UiMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations: ChatCitation[];
  modelId: string | null;
}

function toUi(m: ChatMessage): UiMessage {
  return {
    id: m.message_id,
    role: m.role,
    content: m.content,
    citations: m.citations?.items ?? [],
    modelId: m.model_id,
  };
}

function Citations({ citations, locale }: { citations: ChatCitation[]; locale: Locale }) {
  const [open, setOpen] = useState(false);
  if (citations.length === 0) return null;
  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-2xs font-medium text-fg-link underline-offset-2 hover:underline"
      >
        {bi(locale, 'Fuentes', 'Sources')} ({citations.length})
      </button>
      {open ? (
        <ul className="mt-1 space-y-1">
          {citations.map((c, i) => (
            <li
              key={`${c.query_hash}-${i}`}
              className="rounded-sbs border border-border bg-surface px-2 py-1 text-2xs"
            >
              <div className="flex items-center gap-1.5">
                <Badge variant="source">{c.tool}</Badge>
                <span className="font-mono text-fg-subtle">{c.query_hash}</span>
              </div>
              <div className="mt-0.5 text-fg-muted">
                {bi(locale, 'Filas', 'Rows')}: {c.row_ids_returned.length}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function InsightChatbotPanel({ locale, initialSession, suggestedQuestions }: PanelProps) {
  const [open, setOpen] = useState(true);
  const [sessionId, setSessionId] = useState<string | null>(initialSession?.session_id ?? null);
  const [messages, setMessages] = useState<UiMessage[]>(
    (initialSession?.messages ?? []).map(toUi),
  );
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function send(text: string) {
    const content = text.trim();
    if (!content || pending) return;
    setError(null);
    setInput('');
    const userMsg: UiMessage = {
      id: `local-${Date.now()}`,
      role: 'user',
      content,
      citations: [],
      modelId: null,
    };
    setMessages((prev) => [...prev, userMsg]);
    start(async () => {
      const res = await sendChatAction(sessionId, content);
      if (!res.ok || !res.answer) {
        setError(bi(locale, `No se pudo responder (${res.status}).`, `Could not answer (${res.status}).`));
        return;
      }
      if (res.sessionId) setSessionId(res.sessionId);
      const items =
        res.citations && typeof res.citations === 'object'
          ? ((res.citations as { items?: ChatCitation[] }).items ?? [])
          : [];
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: res.answer as string,
          citations: items,
          modelId: null,
        },
      ]);
    });
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-sbs border border-border-strong bg-surface px-3 py-2 text-xs font-medium text-brand-navy hover:bg-surface-subtle"
      >
        <MessageSquare className="h-4 w-4" aria-hidden="true" />
        {bi(locale, 'Asistente de Insights', 'Insight Chatbot')}
      </button>
    );
  }

  return (
    <aside className="flex h-full max-h-[calc(100vh-7rem)] w-full flex-col rounded-sbs border border-border bg-surface-subtle">
      <header className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-fg">
          <MessageSquare className="h-4 w-4 text-brand-cyan" aria-hidden="true" />
          {bi(locale, 'Asistente de Insights', 'Insight Chatbot')}
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label={bi(locale, 'Contraer', 'Collapse')}
          className="rounded-sbs p-1 text-fg-muted hover:bg-surface hover:text-fg"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </header>

      {suggestedQuestions.length > 0 ? (
        <div className="border-b border-border px-3 py-2">
          <p className="mb-1 text-2xs font-medium uppercase tracking-wide text-fg-subtle">
            {bi(locale, 'Preguntas sugeridas', 'Suggested questions')}
          </p>
          <div className="flex flex-col gap-1">
            {suggestedQuestions.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => send(q)}
                disabled={pending}
                className="rounded-sbs border border-border bg-surface px-2 py-1 text-left text-2xs text-fg hover:border-brand-cyan disabled:opacity-50"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="flex-1 space-y-2 overflow-y-auto px-3 py-2">
        {messages.length === 0 ? (
          <p className="text-xs text-fg-muted">
            {bi(locale, 'Escribe una pregunta para empezar.', 'Ask a question to begin.')}
          </p>
        ) : (
          messages.map((m) => (
            <div
              key={m.id}
              className={
                m.role === 'user'
                  ? 'ml-6 rounded-sbs bg-brand-navy px-2.5 py-1.5 text-xs text-fg-inverted'
                  : 'mr-6 rounded-sbs border border-border bg-surface px-2.5 py-1.5 text-xs text-fg'
              }
            >
              <p className="whitespace-pre-wrap leading-snug">{m.content}</p>
              {m.role === 'assistant' ? (
                <Citations citations={m.citations} locale={locale} />
              ) : null}
            </div>
          ))
        )}
        {pending ? (
          <p className="text-2xs text-fg-subtle">{bi(locale, 'Pensando…', 'Thinking…')}</p>
        ) : null}
        {error ? <p className="text-2xs text-severity-high-fg">{error}</p> : null}
      </div>

      <form
        className="flex items-center gap-1.5 border-t border-border px-3 py-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={bi(locale, 'Pregunta…', 'Ask…')}
          className="flex-1 rounded-sbs border border-border bg-surface px-2.5 py-1.5 text-xs text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        />
        <Button type="submit" size="sm" disabled={pending || input.trim().length === 0}>
          {bi(locale, 'Enviar', 'Send')}
        </Button>
      </form>
    </aside>
  );
}
