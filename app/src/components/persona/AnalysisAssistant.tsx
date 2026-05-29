/* eslint-disable i18next/no-literal-string */
'use client';

import { Bot, MessageCircle, Send, User, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import type { Locale } from '@/i18n';
import { bi } from '@/lib/bi';

// Floating analysis assistant. REAL: every answer comes from
// POST /app/api/aggregates/chat, which composes a numeric reply from live
// /v1/internal/findings. No hardcoded answers, no fake "thinking" timer —
// the loading state tracks the actual fetch. Not a live LLM; it is analysis
// grounded in the complaint data.

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
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, pending]);

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
      setMessages((p) => [...p, { role: 'assistant', text: d.answer ?? bi(locale, 'Sin respuesta.', 'No answer.') }]);
    } catch {
      setMessages((p) => [...p, { role: 'assistant', text: bi(locale, 'Asistente no disponible.', 'Assistant unavailable.') }]);
    } finally {
      setPending(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-full border border-border-strong bg-brand-navy px-4 py-2.5 text-sm font-medium text-fg-inverted shadow-xl hover:bg-brand-navy/90"
      >
        <MessageCircle className="h-4 w-4" aria-hidden="true" />
        {bi(locale, 'Asistente de Análisis', 'Analysis Assistant')}
      </button>
    );
  }

  return (
    <aside className="fixed bottom-5 right-5 z-50 flex h-[80vh] max-h-[680px] w-[min(92vw,460px)] flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-2xl">
      <header className="flex items-start justify-between gap-2 border-b border-border bg-brand-navy px-4 py-3 text-fg-inverted">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-white/15">
            <Bot className="h-4 w-4" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight">{bi(locale, 'Asistente de Análisis', 'Analysis Assistant')}</p>
            <p className="text-2xs text-white/70">{bi(locale, 'Análisis sobre los datos reales de reclamos', 'Analysis grounded in real complaint data')}</p>
          </div>
        </div>
        <button type="button" onClick={() => setOpen(false)} aria-label={bi(locale, 'Cerrar', 'Close')} className="rounded-sbs p-1 hover:bg-white/10">
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto bg-surface-subtle/30 px-3 py-3">
        {messages.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface p-3 text-xs text-fg-muted">
            {bi(
              locale,
              'Hago consultas sobre los datos reales de reclamos (no es un LLM en vivo). Elige una pregunta o escribe la tuya.',
              'I answer from the real complaint data (not a live LLM). Pick a question or type your own.',
            )}
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={`flex items-end gap-2 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${m.role === 'user' ? 'bg-brand-navy text-fg-inverted' : 'bg-brand-cyan/20 text-brand-navy'}`}>
                {m.role === 'user' ? <User className="h-3.5 w-3.5" aria-hidden="true" /> : <Bot className="h-3.5 w-3.5" aria-hidden="true" />}
              </div>
              <div
                className={
                  m.role === 'user'
                    ? 'max-w-[78%] rounded-2xl rounded-br-sm bg-brand-navy px-3 py-2 text-xs leading-relaxed text-fg-inverted'
                    : 'max-w-[82%] rounded-2xl rounded-bl-sm border border-border bg-surface px-3 py-2 text-xs leading-relaxed text-fg'
                }
              >
                <p className="whitespace-pre-wrap">{m.text}</p>
              </div>
            </div>
          ))
        )}
        {pending ? (
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-cyan/20 text-brand-navy">
              <Bot className="h-3.5 w-3.5" aria-hidden="true" />
            </div>
            <div className="flex gap-1 rounded-2xl rounded-bl-sm border border-border bg-surface px-3 py-2.5">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-fg-subtle [animation-delay:-0.3s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-fg-subtle [animation-delay:-0.15s]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-fg-subtle" />
            </div>
          </div>
        ) : null}
      </div>

      <div className="border-t border-border bg-surface px-3 py-2.5">
        {messages.length === 0 ? (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {QUICK_PROMPTS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => ask(q)}
                disabled={pending}
                className="rounded-full border border-border bg-surface-subtle px-2.5 py-1 text-2xs text-fg hover:border-brand-cyan disabled:opacity-50"
              >
                {q}
              </button>
            ))}
          </div>
        ) : null}
        <form className="flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={bi(locale, 'Escribe tu pregunta…', 'Type your question…')}
            className="flex-1 rounded-full border border-border bg-surface px-3.5 py-2 text-xs text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          />
          <button
            type="submit"
            disabled={pending || input.trim().length === 0}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-navy text-fg-inverted disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </form>
      </div>
    </aside>
  );
}
