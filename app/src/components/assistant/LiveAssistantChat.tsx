// SPDX-License-Identifier: Apache-2.0
/* eslint-disable i18next/no-literal-string */
// Live chat box for the supervisor assistant. Replaces the disabled
// textarea on /app/assistant when Azure OpenAI is reachable. Falls back
// to a clear "Modo demo" banner if the script returns no_api_key.

'use client';

import { useCallback, useRef, useState } from 'react';
import { Loader2, Send, Sparkles, User } from 'lucide-react';

import { Card, CardBody } from '@/components/ui';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  tools?: Array<{ name: string; args: Record<string, unknown> }>;
}

interface Props {
  csrfToken: string;
  labels: {
    placeholder: string;
    send: string;
    thinking: string;
    user_label: string;
    bot_label: string;
    demo_mode: string;
    powered_by: string;
  };
}

export function LiveAssistantChat({ csrfToken, labels }: Props) {
  const [history, setHistory] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy) return;
    const userMsg: Message = { role: 'user', content: text };
    setHistory((h) => [...h, userMsg]);
    setInput('');
    setBusy(true);
    try {
      const messages = [...history, userMsg].map((m) => ({
        role: m.role,
        content: m.content,
      }));
      const r = await fetch('/app/api/demo/assistant', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-sbs-csrf': csrfToken,
        },
        body: JSON.stringify({ messages }),
      });
      const json = (await r.json()) as {
        ok?: boolean;
        answer?: string;
        error?: string;
        model?: string;
        tool_calls?: Array<{ name: string; args: Record<string, unknown> }>;
      };
      if (json.error === 'no_api_key') {
        setDemoMode(true);
      }
      if (json.model) setModel(json.model);
      const replyText = json.answer || json.error || 'Sin respuesta.';
      setHistory((h) => [
        ...h,
        {
          role: 'assistant',
          content: replyText,
          tools: json.tool_calls?.map(({ name, args }) => ({ name, args })),
        },
      ]);
    } catch (exc) {
      setHistory((h) => [
        ...h,
        { role: 'assistant', content: `Error: ${String(exc)}` },
      ]);
    } finally {
      setBusy(false);
      requestAnimationFrame(() => {
        if (scrollRef.current) {
          scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
      });
    }
  }, [input, busy, history, csrfToken]);

  return (
    <Card className="border-border">
      <CardBody className="space-y-3 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 rounded-sbs border border-status-resolved-border bg-status-resolved-bg/40 px-2 py-0.5 font-mono text-2xs uppercase tracking-wider text-status-resolved-fg">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-status-resolved-fg" />
            {/* eslint-disable-next-line i18next/no-literal-string */}
            LIVE
          </span>
          {model ? (
            <span className="font-mono text-2xs text-fg-muted">
              {labels.powered_by} · {model}
            </span>
          ) : null}
          {demoMode ? (
            <span className="rounded-sbs border border-severity-medium-border bg-severity-medium-bg px-2 py-0.5 font-mono text-2xs uppercase tracking-wider text-severity-medium-fg">
              {labels.demo_mode}
            </span>
          ) : null}
        </div>

        {history.length > 0 ? (
          <div
            ref={scrollRef}
            className="max-h-72 space-y-2 overflow-y-auto rounded-sbs border border-border-subtle bg-surface-subtle px-3 py-2"
          >
            {history.map((m, i) => (
              <div key={i}>
                {m.role === 'user' ? (
                  <div className="rounded-sbs border border-border-subtle bg-surface px-2.5 py-1.5">
                    <p className="flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-fg-muted">
                      <User className="h-3 w-3" /> {labels.user_label}
                    </p>
                    <p className="mt-1 text-sm text-fg">{m.content}</p>
                  </div>
                ) : (
                  <div className="rounded-sbs border border-brand-cyan/30 bg-brand-cyan/5 px-2.5 py-1.5">
                    <p className="flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-brand-navy">
                      <Sparkles className="h-3 w-3 text-brand-gold" />{' '}
                      {labels.bot_label}
                    </p>
                    {m.tools && m.tools.length > 0 ? (
                      <p className="mt-0.5 font-mono text-2xs text-fg-muted">
                        {/* eslint-disable-next-line i18next/no-literal-string */}
                        tool_calls:{' '}
                        {m.tools.map((t) => t.name).join(', ')}
                      </p>
                    ) : null}
                    <p className="mt-1 whitespace-pre-wrap text-sm leading-snug text-fg">
                      {m.content}
                    </p>
                  </div>
                )}
              </div>
            ))}
            {busy ? (
              <div className="flex items-center gap-2 text-sm text-fg-muted">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {labels.thinking}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="flex items-start gap-2">
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder={labels.placeholder}
            disabled={busy}
            className="flex-1 resize-none rounded-sbs border border-border bg-surface px-3 py-2 text-sm text-fg focus:border-brand-cyan focus:outline-none disabled:opacity-50"
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={busy || !input.trim()}
            className="inline-flex h-9 items-center justify-center gap-1 rounded-sbs bg-brand-navy px-3 text-sm font-medium text-fg-inverted hover:bg-brand-navy/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" /> {labels.send}
          </button>
        </div>
      </CardBody>
    </Card>
  );
}
