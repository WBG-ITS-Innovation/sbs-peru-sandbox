/* eslint-disable i18next/no-literal-string */
'use client';

import { MessageCircle, Send, X } from 'lucide-react';
import { useState } from 'react';

import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

// Floating analysis assistant. REAL: every answer comes from
// POST /app/api/aggregates/chat, which composes a numeric reply from live
// /v1/internal/findings. No hardcoded answers, no fake "thinking" timer —
// the loading state tracks the actual fetch.

interface ChatMsg {
  role: 'user' | 'assistant';
  text: string;
}

const QUICK_PROMPTS = [
  '¿Qué patrones de fraude hay esta semana?',
  '¿Cuántos reclamos de severidad alta hay?',
  '¿Qué institución concentra más reclamos?',
  'Resume el estado de los agregados',
];

export function AnalysisAssistant({ locale }: { locale: Locale }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(false);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || pending) return;
    setInput('');
    setMessages((p) => [...p, { role: 'user', text: q }]);
    setPending(true);
    try {
      const r = await fetch('/app/api/aggregates/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: q }),
        cache: 'no-store',
      });
      const d = (await r.json()) as { answer?: string };
      setMessages((p) => [
        ...p,
        { role: 'assistant', text: d.answer ?? bi(locale, 'Sin respuesta.', 'No answer.') },
      ]);
    } catch {
      setMessages((p) => [
        ...p,
        { role: 'assistant', text: bi(locale, 'Asistente no disponible.', 'Assistant unavailable.') },
      ]);
    } finally {
      setPending(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-sbs border border-border-strong bg-brand-navy px-3 py-2 text-sm font-medium text-fg-inverted shadow-lg hover:bg-brand-navy/90"
      >
        <MessageCircle className="h-4 w-4" aria-hidden="true" />
        {bi(locale, 'Asistente de Análisis', 'Analysis Assistant')}
      </button>
    );
  }

  return (
    <aside className="fixed bottom-4 right-4 z-50 flex max-h-[70vh] w-[360px] flex-col rounded-sbs border border-border bg-surface shadow-lg">
      <header className="flex items-center justify-between border-b border-border bg-brand-navy px-3 py-2 text-fg-inverted">
        <span className="flex items-center gap-1.5 text-sm font-semibold">
          <MessageCircle className="h-4 w-4" aria-hidden="true" />
          {bi(locale, 'Asistente de Análisis', 'Analysis Assistant')}
        </span>
        <button type="button" onClick={() => setOpen(false)} aria-label={bi(locale, 'Cerrar', 'Close')} className="rounded-sbs p-1 hover:bg-white/10">
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </header>
      <div className="flex-1 space-y-2 overflow-y-auto px-3 py-2">
        {messages.length === 0 ? (
          <p className="text-xs text-fg-muted">
            {bi(locale, 'Respuestas basadas en los datos reales de reclamos. Elige una pregunta o escribe la tuya.', 'Answers grounded in real complaint data. Pick a question or type your own.')}
          </p>
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              className={
                m.role === 'user'
                  ? 'ml-6 rounded-sbs bg-brand-navy px-2.5 py-1.5 text-xs text-fg-inverted'
                  : 'mr-6 rounded-sbs border border-border bg-surface-subtle px-2.5 py-1.5 text-xs text-fg'
              }
            >
              <p className="whitespace-pre-wrap leading-snug">{m.text}</p>
            </div>
          ))
        )}
        {pending ? <p className="text-2xs text-fg-subtle">{bi(locale, 'Consultando los datos…', 'Querying the data…')}</p> : null}
      </div>
      <div className="border-t border-border px-3 py-2">
        <div className="mb-1.5 flex flex-col gap-1">
          {QUICK_PROMPTS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => ask(q)}
              disabled={pending}
              className="rounded-sbs border border-border bg-surface px-2 py-1 text-left text-2xs text-fg hover:border-brand-cyan disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>
        <form className="flex items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={bi(locale, 'Pregunta…', 'Ask…')}
            className="flex-1 rounded-sbs border border-border bg-surface px-2.5 py-1.5 text-xs text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          />
          <button
            type="submit"
            disabled={pending || input.trim().length === 0}
            className="rounded-sbs bg-brand-navy px-2.5 py-1.5 text-fg-inverted disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </form>
      </div>
    </aside>
  );
}
