#!/usr/bin/env python
"""Backend for the demo /app/assistant chat box.

Reads a JSON line from stdin with shape:
    {"messages": [{"role":"user","content":"..."}], "model": "..."}

Calls Azure OpenAI chat completions with three tool functions backed
by the local Postgres so the assistant can answer real questions about
the supervisor's complaint data:

    * query_complaints_count(since_hours: int = 24)
    * query_complaints_by_motivo(top: int = 5, since_days: int = 7)
    * query_anomalies_active(min_score: float = 0.70)

Prints a single JSON line on stdout:
    {"ok": true, "answer": "...", "model": "...", "tool_calls": [...]}
or:
    {"ok": false, "error": "..."}

PII safety: the tool functions return aggregate counts and labels; no
PII leaves the database.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
import urllib.request
import urllib.error


# When invoked from the Next.js dev server, only the Next process env
# is inherited (which doesn't include the repo-root .env). Fall back to
# parsing .env so the demo works without a separate app/.env.local copy.
def _load_repo_env() -> None:
    if os.environ.get("AZURE_OPENAI_API_KEY"):
        return
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_repo_env()


DSN = os.environ.get(
    "SBS_API_DATABASE_URL_SYNC",
    "postgresql://sbs:sbs@localhost:5432/sbs_dev",  # pragma: allowlist secret
).replace("+asyncpg", "")


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def query_complaints_count(since_hours: int = 24) -> dict:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM complaints "
            "WHERE received_at > now() - (%s || ' hours')::interval",
            (since_hours,),
        )
        n = int(cur.fetchone()[0])
        cur.execute(
            "SELECT institution_id, COUNT(*) FROM complaints "
            "WHERE received_at > now() - (%s || ' hours')::interval "
            "GROUP BY institution_id ORDER BY COUNT(*) DESC LIMIT 5",
            (since_hours,),
        )
        by_inst = [{"institution_id": r[0], "count": int(r[1])} for r in cur.fetchall()]
    return {"window_hours": since_hours, "total": n, "by_institution": by_inst}


def query_complaints_by_motivo(top: int = 5, since_days: int = 7) -> dict:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT motivo_code, COUNT(*) FROM complaints "
            "WHERE received_at > now() - (%s || ' days')::interval "
            "GROUP BY motivo_code ORDER BY 2 DESC LIMIT %s",
            (since_days, top),
        )
        rows = [{"motivo_code": r[0], "count": int(r[1])} for r in cur.fetchall()]
    return {"window_days": since_days, "items": rows}


def query_anomalies_active(min_score: float = 0.70) -> dict:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT r.complaint_id,
                   r.final_output->'anomaly'->>'composite_score' AS score
            FROM agent_runs r
            WHERE r.agent_name = 'investigation'
              AND r.final_output->'anomaly'->>'composite_score' IS NOT NULL
              AND (r.final_output->'anomaly'->>'composite_score')::float >= %s
            ORDER BY 2 DESC LIMIT 10
            """,
            (min_score,),
        )
        rows = [{"complaint_id": r[0], "score": float(r[1])} for r in cur.fetchall()]
    return {"min_score": min_score, "count": len(rows), "items": rows}


_TOOL_FNS = {
    "query_complaints_count": query_complaints_count,
    "query_complaints_by_motivo": query_complaints_by_motivo,
    "query_anomalies_active": query_anomalies_active,
}


_TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "query_complaints_count",
            "description": "Total complaints in the last N hours, broken down by institution.",
            "parameters": {
                "type": "object",
                "properties": {
                    "since_hours": {"type": "integer", "minimum": 1, "maximum": 720, "default": 24},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_complaints_by_motivo",
            "description": "Top N motivos (reason codes) for complaints in the last K days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "top": {"type": "integer", "minimum": 1, "maximum": 25, "default": 5},
                    "since_days": {"type": "integer", "minimum": 1, "maximum": 90, "default": 7},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_anomalies_active",
            "description": "Complaints whose composite anomaly score is at or above min_score.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_score": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.70},
                },
            },
        },
    },
]


SYSTEM_PROMPT = (
    "Eres el asistente de la SBS para la supervisora del Departamento de "
    "Conducta de Mercado. Responde en español neutro, con tono sobrio y "
    "técnico-regulatorio. Usa las herramientas para consultar datos reales "
    "antes de responder con números. Si no estás seguro, dilo. No inventes "
    "cifras. Cita siempre el complaint_id cuando sea relevante."
)


# ---------------------------------------------------------------------------
# Azure OpenAI HTTP call (no SDK to keep cold-start small)
# ---------------------------------------------------------------------------


def _azure_chat(messages: list, *, tools: list | None = None) -> dict:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01")
    key = os.environ["AZURE_OPENAI_API_KEY"]
    url = (
        f"{endpoint}/openai/deployments/{deployment}/chat/completions"
        f"?api-version={api_version}"
    )
    body: dict[str, Any] = {"messages": messages}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "api-key": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"bad json: {exc}"}))
        return 0

    user_messages = payload.get("messages") or []
    if not user_messages:
        print(json.dumps({"ok": False, "error": "no messages"}))
        return 0

    if not os.environ.get("AZURE_OPENAI_API_KEY"):
        print(json.dumps({
            "ok": False,
            "error": "no_api_key",
            "answer": "Modo demo · respuestas pre-generadas (AZURE_OPENAI_API_KEY no configurada).",
        }))
        return 0

    messages: list = [{"role": "system", "content": SYSTEM_PROMPT}, *user_messages]
    tool_call_log: list[dict] = []

    try:
        # First call — let the model decide whether to invoke a tool.
        resp = _azure_chat(messages, tools=_TOOL_SPECS)
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message") or {}

        # Resolve tool calls (single round; the demo doesn't need chains).
        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            messages.append(msg)
            for tc in tool_calls:
                fn = tc.get("function") or {}
                fn_name = fn.get("name")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                impl = _TOOL_FNS.get(fn_name)
                if impl is None:
                    result = {"error": f"unknown tool {fn_name}"}
                else:
                    try:
                        result = impl(**args)
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": f"{type(exc).__name__}: {exc}"}
                tool_call_log.append({"name": fn_name, "args": args, "result": result})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "content": json.dumps(result, ensure_ascii=False),
                })
            # Second call — synthesise the final answer.
            resp = _azure_chat(messages)
            msg = (resp.get("choices") or [{}])[0].get("message") or {}

        answer = msg.get("content") or ""
        print(json.dumps({
            "ok": True,
            "answer": answer,
            "model": resp.get("model") or os.environ.get("AZURE_OPENAI_DEPLOYMENT"),
            "tool_calls": tool_call_log,
        }, ensure_ascii=False))
        return 0
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({"ok": False, "error": f"azure HTTP {exc.code}: {body[:300]}"}))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 0


if __name__ == "__main__":
    sys.exit(main())
