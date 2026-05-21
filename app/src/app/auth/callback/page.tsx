// Placeholder. The OAuth callback handler lands with the OAuth commit
// (next). The route is reserved here so that Keycloak's allowed-redirect
// list and the FastAPI reverse proxy can be configured to point at
// /app/auth/callback before the handler itself ships.
export default function AuthCallbackPage() {
  return (
    <main>
      <h1>Signing you in…</h1>
      <p>OAuth callback handler — landing in the next commit on this branch.</p>
    </main>
  );
}
