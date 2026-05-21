// Placeholder. WS5 lands the approval detail view + four actions
// (approve, approve-with-edits, reject, send-back-to-analyst).
export default function ApprovalDetailPage({ params }: { params: { id: string } }) {
  return (
    <main>
      <h1>Approval {params.id}</h1>
      <p>WS5 — agent reasoning, evidence, four-action HITL gate.</p>
    </main>
  );
}
