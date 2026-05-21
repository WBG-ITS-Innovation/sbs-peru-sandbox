// Placeholder. WS6 lands the read-only audit table (50 rows / page,
// actor / action / object / diff columns, search by actor / action / object).
export default function AuditPage() {
  return (
    <main>
      <h1>Audit</h1>
      <p>WS6 — chronological audit log reading from <code>audit_events</code>.</p>
    </main>
  );
}
