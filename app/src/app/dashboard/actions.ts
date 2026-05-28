'use server';

// Server actions for the demo dashboards (P-RESHAPE-10). Every mutation
// runs server-side: it reads the active persona from the cookie (never
// from client input), attaches the persona's role, and posts to the
// backend through the shared-secret BFF hop. A client cannot widen its
// own role because the role is derived from the cookie here.

import { revalidatePath } from 'next/cache';
import { cookies } from 'next/headers';

import {
  PERSONA_COOKIE,
  activePersona,
  personaCookieOptions,
  personaPost,
} from '@/auth/persona-server';
import { isPersonaSlug, type PersonaConfig } from '@/lib/persona';

const enc = encodeURIComponent;

export interface ActionResult {
  ok: boolean;
  status: number;
  message: string;
}

export async function setPersonaAction(slug: string): Promise<void> {
  if (!isPersonaSlug(slug)) {
    throw new Error(`Unknown persona: ${slug}`);
  }
  cookies().set(PERSONA_COOKIE, slug, personaCookieOptions());
}

export async function clearPersonaAction(): Promise<void> {
  cookies().delete(PERSONA_COOKIE);
}

interface ActionInputs {
  rationale: string;
  summary?: string;
  targetId?: string;
}

type Spec = (
  p: PersonaConfig,
  i: ActionInputs,
) => { path: string; body: Record<string, unknown>; asUser?: boolean };

// action_id → backend call. Keys match api/sbs_api/personas/action_registry.py.
const ACTION_SPECS: Record<string, Spec> = {
  propose_pattern: (p, i) => ({
    path: '/v1/internal/findings/manual',
    body: {
      proposed_by_user_id: p.taskUserId,
      summary: i.summary?.trim() || i.rationale.slice(0, 120),
      rationale: i.rationale,
      institution_code: i.targetId?.trim() || null,
    },
  }),
  flag_complaint_for_review: (p, i) => ({
    path: `/v1/complaints/${enc(i.targetId ?? '')}/flag`,
    body: { actor_user_id: p.taskUserId, rationale: i.rationale },
  }),
  request_enrichment: (p, i) => ({
    path: `/v1/complaints/${enc(i.targetId ?? '')}/request_enrichment`,
    body: { actor_user_id: p.taskUserId, rationale: i.rationale },
  }),
  approve_fi_brief: (p, i) => ({
    path: `/v1/internal/fi_briefs/${enc(i.targetId ?? '')}/approve`,
    body: { actor_id: p.taskUserId, rationale: i.rationale },
  }),
  delegate_pattern: (p, i) => ({
    path: `/v1/internal/findings/${enc(i.targetId ?? '')}/delegate`,
    body: { actor_user_id: p.taskUserId, rationale: i.rationale },
  }),
  defer_pattern: (p, i) => ({
    path: `/v1/internal/findings/${enc(i.targetId ?? '')}/defer`,
    body: { actor_user_id: p.taskUserId, rationale: i.rationale },
  }),
  override_supervisor_decision: (p, i) => ({
    path: `/v1/internal/persona/fi_briefs/${enc(i.targetId ?? '')}/override`,
    body: { actor_id: p.taskUserId, rationale: i.rationale },
  }),
  approve_sector_broadcast_primary: (p, i) => ({
    path: `/v1/internal/sector_broadcast/${enc(i.targetId ?? '')}/approve_primary`,
    body: { actor_id: p.taskUserId, rationale: i.rationale },
  }),
  generate_weekly_digest: (p) => ({
    path: '/v1/internal/exec/digest/generate',
    body: { actor_user_id: p.taskUserId },
  }),
  approve_sector_broadcast_secondary: (p, i) => ({
    path: `/v1/internal/sector_broadcast/${enc(i.targetId ?? '')}/approve_secondary`,
    body: { actor_id: p.taskUserId, rationale: i.rationale },
  }),
  request_deeper_look: (p, i) => ({
    path: '/v1/internal/exec/tasking',
    body: { actor_user_id: p.taskUserId, rationale: i.rationale },
  }),
  acknowledge_digest: (p, i) => ({
    path: `/v1/internal/exec/digest/${enc(i.targetId ?? '')}/acknowledge`,
    body: { actor_user_id: p.taskUserId },
  }),
  annotate_incident: (p, i) => ({
    path: '/v1/internal/ops/incidents',
    body: { actor_user_id: p.taskUserId, note: i.rationale },
  }),
  retry_webhook: (p, i) => ({
    path: `/v1/internal/ops/webhooks/${enc(i.targetId ?? '')}/retry`,
    body: { actor_user_id: p.taskUserId, rationale: i.rationale },
  }),
  requeue_agent_run: (p, i) => ({
    path: `/v1/internal/ops/runs/${enc(i.targetId ?? '')}/requeue`,
    body: { actor_user_id: p.taskUserId, rationale: i.rationale },
  }),
  circuit_break_ingestion: (p, i) => ({
    path: `/v1/internal/ops/circuit_breaker/${enc(i.targetId ?? '')}`,
    body: { actor_user_id: p.taskUserId, action: 'PAUSE', rationale: i.rationale },
  }),
};

function summarize(status: number, data: unknown): string {
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>;
    if (typeof d.detail === 'string') return d.detail;
    if (typeof d.title === 'string') return d.title;
    if (typeof d.status === 'string') return `${d.status}`;
    if (typeof d.finding_id === 'string') return `Created (${d.finding_id})`;
    if (typeof d.brief_id === 'string') return `Brief ${d.brief_id}`;
    if (typeof d.task_id === 'string') return `Task ${d.task_id}`;
  }
  return `HTTP ${status}`;
}

export async function runActionAction(
  actionId: string,
  inputs: ActionInputs,
): Promise<ActionResult> {
  const persona = activePersona();
  if (!persona) return { ok: false, status: 401, message: 'No active persona.' };
  const spec = ACTION_SPECS[actionId];
  if (!spec) return { ok: false, status: 400, message: `Unknown action: ${actionId}` };
  const { path, body, asUser } = spec(persona, inputs);
  const res = await personaPost(persona, path, body, { asUser });
  revalidatePath(`/dashboard/${persona.slug}`);
  return { ok: res.ok, status: res.status, message: summarize(res.status, res.data) };
}

export async function ackTaskAction(taskId: string): Promise<ActionResult> {
  const persona = activePersona();
  if (!persona) return { ok: false, status: 401, message: 'No active persona.' };
  const res = await personaPost(persona, `/v1/internal/cockpit/tasks/${enc(taskId)}/ack`, {
    actor_user_id: persona.taskUserId,
    response: null,
  });
  revalidatePath(`/dashboard/${persona.slug}`);
  return { ok: res.ok, status: res.status, message: summarize(res.status, res.data) };
}

export async function completeTaskAction(taskId: string): Promise<ActionResult> {
  const persona = activePersona();
  if (!persona) return { ok: false, status: 401, message: 'No active persona.' };
  const res = await personaPost(persona, `/v1/internal/cockpit/tasks/${enc(taskId)}/complete`, {
    actor_user_id: persona.taskUserId,
    response: null,
  });
  revalidatePath(`/dashboard/${persona.slug}`);
  return { ok: res.ok, status: res.status, message: summarize(res.status, res.data) };
}

export async function declineTaskAction(
  taskId: string,
  rationale: string,
): Promise<ActionResult> {
  const persona = activePersona();
  if (!persona) return { ok: false, status: 401, message: 'No active persona.' };
  const res = await personaPost(persona, `/v1/internal/cockpit/tasks/${enc(taskId)}/decline`, {
    actor_user_id: persona.taskUserId,
    rationale,
  });
  revalidatePath(`/dashboard/${persona.slug}`);
  return { ok: res.ok, status: res.status, message: summarize(res.status, res.data) };
}

export interface ChatResult {
  ok: boolean;
  status: number;
  sessionId: string | null;
  answer: string | null;
  citations: unknown;
}

export async function sendChatAction(
  sessionId: string | null,
  content: string,
): Promise<ChatResult> {
  const persona = activePersona();
  if (!persona) {
    return { ok: false, status: 401, sessionId, answer: null, citations: null };
  }
  let sid = sessionId;
  if (!sid) {
    const created = await personaPost(persona, '/v1/chatbot/sessions', {}, { asUser: true });
    if (!created.ok) {
      return { ok: false, status: created.status, sessionId: null, answer: null, citations: null };
    }
    sid = (created.data as { session_id?: string })?.session_id ?? null;
  }
  if (!sid) {
    return { ok: false, status: 500, sessionId: null, answer: null, citations: null };
  }
  const res = await personaPost(
    persona,
    `/v1/chatbot/sessions/${enc(sid)}/messages`,
    { content },
    { asUser: true },
  );
  const data = (res.data ?? {}) as Record<string, unknown>;
  const answer =
    (typeof data.answer_text_es === 'string' && data.answer_text_es) ||
    (typeof data.answer_text_en === 'string' && data.answer_text_en) ||
    (typeof data.content === 'string' && data.content) ||
    null;
  return {
    ok: res.ok,
    status: res.status,
    sessionId: sid,
    answer,
    citations: data.citations ?? null,
  };
}
